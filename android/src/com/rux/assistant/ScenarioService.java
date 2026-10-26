package com.rux.assistant;

import android.app.*;
import android.content.*;
import android.content.res.AssetFileDescriptor;
import android.media.*;
import android.os.*;
import android.util.*;
import org.json.JSONObject;
import com.leitianpai.robotsdk.RobotService;
import com.leitianpai.robotsdk.callback.SensorCallback;
import com.leitianpai.robotsdk.message.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Owns SDK, stored choreography, cancellation and repeat scheduling on the robot. */
public final class ScenarioService extends Service {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService hardware=Executors.newSingleThreadExecutor();
    private final Object motorGate=new Object();
    private final ScenarioClock clock=new ScenarioClock();
    private final SessionQueues inbox=new SessionQueues();
    private String displayedQueue="";
    private String activityText="";
    private final LinkedHashMap<String,String> replies=new LinkedHashMap<>();
    private RobotService robot;
    private ScenarioStore store;
    private String startupError, title="Codex";
    private Run current;
    private MediaPlayer player;
    private boolean destroyed;
    private static class Run {
        final AtomicBoolean abort=new AtomicBoolean();
        final long generation;
        final String request, command;
        volatile boolean done, failed;
        boolean audioDone=true;
        Run(long generation,String request,String command){this.generation=generation;this.request=request;this.command=command;}
    }
    @Override public void onCreate() {
        super.onCreate();
        NotificationManager notifications=(NotificationManager)getSystemService(NOTIFICATION_SERVICE);
        notifications.createNotificationChannel(new NotificationChannel("rux-runtime","Rux Assistant",NotificationManager.IMPORTANCE_LOW));
        startForeground(1,new Notification.Builder(this,"rux-runtime").setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Rux Assistant").setContentText("Bộ chạy kịch bản đang sẵn sàng").build());
        try{store=new ScenarioStore(this);}catch(Exception e){startupError=e.toString();Log.e("RuxAssistant","CONFIG_LOAD_FAILED",e);}
        robot=RobotService.getInstance(this);
        handler.post(ticker);
    }
    @Override public IBinder onBind(Intent intent){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int startId) {
        if(intent!=null)ready(new Intent(intent),0);
        return START_NOT_STICKY; // Configuration survives, active motion never resumes on restart.
    }
    private void ready(Intent intent,int attempt) {
        if(destroyed)return;
        if(robot.getAIDL()==null) {
            if(attempt<50)handler.postDelayed(()->ready(intent,attempt+1),100);
            else reply(intent,false,"SDK_TIMEOUT");
            return;
        }
        execute(intent);
    }
    private long now(){return SystemClock.elapsedRealtime();}
    private String str(Intent intent,String key,String fallback){String value=intent.getStringExtra(key);return value==null?fallback:value;}
    private String decode(String value){if(value.length()>24000)throw new IllegalArgumentException("Payload too large");return new String(android.util.Base64.decode(value,android.util.Base64.DEFAULT),StandardCharsets.UTF_8);}
    private String caption(Intent intent){String s=decode(str(intent,"title_b64",""));s=s.replaceAll("[\\p{Cntrl}]"," ").trim();return s.substring(0,Math.min(160,s.length()));}
    private void reply(Intent intent,boolean ok,String detail){reply(str(intent,"request","launcher"),ok,detail);}
    private void reply(String request,boolean ok,String detail) {
        String line=(ok?"OK":"FAILED")+" request="+request+" "+detail;
        replies.put(request,line);while(replies.size()>256)replies.remove(replies.keySet().iterator().next());
        if(ok)Log.i("RuxAssistant",line);else Log.e("RuxAssistant",line);
    }
    private String snapshot(){return "revision="+(store==null?"unavailable":store.revision)+" state="+clock.state+" active="+clock.active+" generation="+clock.generation;}
    private void execute(Intent intent) {
        String request=str(intent,"request",UUID.randomUUID().toString());intent.putExtra("request",request);
        if(replies.containsKey(request)){String cached=replies.get(request);if(cached!=null)Log.i("RuxAssistant",cached+" replay=true");return;}
        replies.put(request,null);
        String command=str(intent,"command","status"), value=str(intent,"value","");
        try {
            if(command.equals("sessions")){reply(intent,true,"command=sessions data="+sessionsJSON(value));return;}
            if(command.equals("hold-sessions")){inbox.held=true;pause("manual-hold",false);reply(intent,true,"held=true");return;}
            if(command.equals("release-sessions")){inbox.held=false;clock.context="";SessionQueues.Entry e=inbox.selected();if(e!=null&&!e.blocked)e.dirty=true;pumpInbox();reply(intent,true,"held=false");return;}
            if(command.equals("session-state")||command.equals("session-heartbeat")||command.equals("select-session")){
                if(store==null)throw new IllegalStateException(startupError);
                JSONObject envelope=new JSONObject(decode(value));
                String source=envelope.getString("source"),session=envelope.getString("session_id");
                if(command.equals("select-session")){inbox.select(source,session,now());pumpInbox();reply(intent,true,"selected=true");return;}
                Object rawSeq=envelope.get("sequence");
                if(!(rawSeq instanceof Integer)&&!(rawSeq instanceof Long))throw new IllegalArgumentException("Sequence must be an integer");
                long seq=((Number)rawSeq).longValue();
                if(command.equals("session-heartbeat")){
                    boolean active=inbox.heartbeat(source,session,seq,now());SessionQueues.Entry e=inbox.get(source,session);
                    if(active&&e==inbox.selected())active=clock.heartbeat(e.context(),now());
                    reply(intent,true,"command=session-heartbeat active="+active);return;
                }
                String label=envelope.optString("title",source);label=label.replaceAll("[\\p{Cntrl}]"," ").trim();if(label.length()>160)label=label.substring(0,160);
                SessionQueues.Entry accepted=inbox.accept(source,session,envelope.getString("turn_id"),envelope.getString("state"),label,cleanActivity(envelope.optString("activity","")),seq,
                    envelope.optBoolean("quiet",false),envelope.optBoolean("no_motion",false),now());
                pumpInbox();reply(intent,true,"command=session-state accepted=true stale="+(accepted==null)+" selected="+(accepted!=null&&accepted==inbox.selected()));return;
            }
            if(command.equals("heartbeat")) {
                boolean active=clock.heartbeat(str(intent,"context",""),now());
                reply(intent,true,"command=heartbeat active="+active);return;
            }
            if(command.equals("pause")||command.equals("motion-stop")||command.equals("stop")) {
                inbox.stopAll();displayedQueue="";pause("explicit-stop",false);
                hardware.execute(()->handler.post(()->reply(intent,true,"command=web-stop "+snapshot())));return;
            }
            if(store==null)throw new IllegalStateException(startupError);
            if(command.equals("status")){reply(intent,true,"command=status "+snapshot());return;}
            if(command.equals("configure")) {
                JSONObject config=new JSONObject(decode(value));store.validate(config);
                inbox.stopAll();displayedQueue="";pause("configure",false);store.save(config);clock.context="";
                reply(intent,true,"command=configure "+snapshot());return;
            }
            if(command.equals("set-state")||command.equals("state")||command.equals("play")||command.equals("pose")) {
                inbox.stopAll();displayedQueue="";
                activityText=cleanActivity(decode(str(intent,"activity_b64","")));
                boolean changed=applyState(value,str(intent,"context",request),caption(intent),intent.getBooleanExtra("quiet",false),
                    intent.getBooleanExtra("no_motion",false),command.equals("play")||command.equals("pose"),command.equals("pose"),request);
                reply(intent,true,"command="+command+" accepted=true changed="+changed+" "+snapshot());return;
            }
            // Explicit web trials pause the automatic episode before starting a bounded run.
            JSONObject spec;
            if(command.equals("preview")||command.equals("scenario"))spec=new JSONObject(decode(value));
            else if(command.equals("motion")&&value.equals("tiny-shake"))spec=new JSONObject().put("motion",24).put("steps",2);
            else if(command.equals("audio"))spec=new JSONObject().put("audio",value).put("face","cute_happy");
            else if(command.equals("face")&&value.matches("h[0-9]{4}"))spec=new JSONObject().put("face",value);
            else if(command.equals("sound")&&value.matches("a[0-9]{4}"))spec=new JSONObject().put("sound",value);
            else if(command.equals("say")&&!value.isEmpty()&&value.length()<=500)spec=new JSONObject().put("tts",value);
            else throw new IllegalArgumentException("Unknown command");
            validateTrial(spec);
            inbox.stopAll();displayedQueue="";activityText="";pause("manual-preview",false);
            String face=spec.optString("face","idle");
            if(!face.matches("h[0-9]{4}"))render(face,spec.optString("state",face),caption(intent));
            launch(spec,request,command,true);
        } catch(Exception e){reply(intent,false,command+" "+e.getMessage());Log.e("RuxAssistant","COMMAND_ERROR",e);}
    }
    private String cleanActivity(String value){value=value.replaceAll("[\\p{Cntrl}\\p{Cf}]"," ").trim();return value.substring(0,Math.min(80,value.length()));}
    private boolean applyState(String value,String nextContext,String nextTitle,boolean quiet,boolean noMotion,boolean oneShot,boolean pose,String request)throws Exception {
        JSONObject preset=store.preset(value);
        if(nextContext.length()>1000)throw new IllegalArgumentException("Context too long");
        if(!nextTitle.isEmpty())title=nextTitle;
        boolean changed=clock.activate(value,nextContext,oneShot||noMotion?0:preset.getInt("repeat"),now());
        if(!changed&&noMotion){clock.repeat=0;cancelRun();}
        JSONObject visible=clock.state.equals(value)?preset:store.preset(clock.state);
        if(!visible.getString("face").matches("h[0-9]{4}"))render(visible.getString("face"),clock.state,title);
        if(changed){
            cancelRun();JSONObject spec=new JSONObject(preset.toString());spec.put("duration_ms",3000).put("steps",1);
            if(!pose&&!quiet&&(value.equals("attention")||value.equals("completed")))spec.put("audio","voice-"+store.data.getString("voice")+"-"+value+".wav");
            if(noMotion)spec.put("motion",0).put("motion2",0).put("ears",0);
            launch(spec,request,"state",false);
        }
        return changed;
    }
    private boolean runFinished(){return current==null||(current.done&&(current.audioDone||current.abort.get()));}
    private void pumpInbox()throws Exception {
        SessionQueues.Entry entry=inbox.choose(now(),runFinished());
        if(entry==null){if(!displayedQueue.isEmpty()){pause("queue-unavailable",false);displayedQueue="";}return;}
        if(entry.dirty||!entry.key().equals(displayedQueue)){
            displayedQueue=entry.key();entry.dirty=false;activityText=entry.activity;
            applyState(entry.state,entry.context(),entry.title,entry.quiet,entry.noMotion,false,false,"queue-"+entry.source+"-"+entry.sequence);
            Log.i("RuxAssistant","QUEUE_SELECTED source="+entry.source+" session="+entry.session+" state="+entry.state);
        }
    }
    private String sessionsJSON(String value)throws Exception {
        int offset=value.isEmpty()?0:new JSONObject(decode(value)).optInt("offset",0);
        if(offset<0||offset>64)throw new IllegalArgumentException("Invalid page");
        org.json.JSONArray rows=new org.json.JSONArray();int index=0;
        for(SessionQueues.Entry e:inbox.entries()){
            if(index++<offset)continue;if(rows.length()>=2)break;
            rows.put(new JSONObject().put("source",e.source).put("session_id",e.session).put("turn_id",e.turn)
            .put("state",e.state).put("title",e.title).put("activity",e.activity).put("selected",e==inbox.selected()).put("blocked",e.blocked).put("live",e.lease>now()).put("sequence",e.sequence));
        }
        JSONObject page=new JSONObject().put("queues",rows).put("next_offset",offset+rows.length()<inbox.entries().size()?offset+rows.length():-1);
        return android.util.Base64.encodeToString(page.toString().getBytes(StandardCharsets.UTF_8),android.util.Base64.NO_WRAP);
    }
    private void validateTrial(JSONObject spec)throws Exception {
        String face=spec.optString("face","idle");
        if(!face.matches("h[0-9]{4}|working|attention|completed|idle|failed|cute_happy|cute_shy|cute_curious|cute_sleepy|cute_love|cute_wink|cute_sad"))throw new IllegalArgumentException("Unknown face");
        for(String key:new String[]{"motion","motion2","ears","angle","steps","duration_ms","light"})if(spec.has(key)) {
            int min=key.equals("light")?-1:key.equals("angle")||key.equals("steps")?1:key.equals("duration_ms")?800:0;
            int max=(key.equals("motion")||key.equals("motion2"))?80:key.equals("ears")?3:key.equals("angle")?45:key.equals("steps")?2:key.equals("light")?8:4000;
            ScenarioStore.number(spec,key,min,max);
        }
        if(spec.has("audio")){
            String asset=spec.getString("audio");if(!asset.matches("voice-[a-z0-9-]+\\.wav"))throw new IllegalArgumentException("Invalid audio");
            try(AssetFileDescriptor fd=getAssets().openFd(asset)){if(fd.getLength()>8*1024*1024)throw new IllegalArgumentException("Oversized audio");}
        }
    }
    private void render(String face,String state,String caption) {
        String note=state.equals("working")?activityText:"";
        getSharedPreferences("display",MODE_PRIVATE).edit().putString("face",face).putString("state",state).putString("title",caption).putString("activity",note).apply();
        Intent view=new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_SINGLE_TOP);
        view.putExtra("render_face",face).putExtra("render_state",state).putExtra("render_title",caption).putExtra("render_activity",note);
        startActivity(view);
    }
    private final Runnable ticker=new Runnable(){public void run(){
        if(destroyed)return;
        int tick=clock.tick(now());
        if(tick==-2){cancelRun();render("idle","idle",title);Log.i("RuxAssistant","COMPLETED_TIMEOUT state=idle after_ms=60000");}
        else if(tick==-1){inbox.blockSelected();pause("lease-expired",false);}
        else if(tick>0) {
            try {
                // Never queue a catch-up run behind an unfinished one.
                if(current==null||current.done) {
                    JSONObject spec=new JSONObject(store.preset(clock.state).toString());
                    spec.put("duration_ms",3000).put("steps",1);
                    launch(spec,"repeat-"+clock.generation+"-"+now(),"repeat",false);
                }
            }catch(Exception e){pause("repeat-error",true);Log.e("RuxAssistant","REPEAT_FAILED",e);}
        }
        try{pumpInbox();}catch(Exception e){inbox.blockSelected();pause("queue-error",true);Log.e("RuxAssistant","QUEUE_ERROR",e);}
        handler.postDelayed(this,250);
    }};
    private void cancelRun() {
        if(current!=null)current.abort.set(true);
        if(player!=null){player.release();player=null;}
        synchronized(motorGate){try{if(robot.getAIDL()!=null)robot.robotCloseMotor();}catch(Exception e){Log.e("RuxAssistant","CANCEL_MOTOR_ERROR",e);}}
    }
    private void pause(String reason,boolean restFace) {
        clock.pause();cancelRun();Log.i("RuxAssistant","RUNTIME_PAUSED reason="+reason+" "+snapshot());
        if(restFace)render("idle","idle",title);
    }
    private void sensorStop(Run run) {
        run.abort.set(true);
        synchronized(motorGate){try{robot.robotCloseMotor();}catch(Exception e){Log.e("RuxAssistant","SENSOR_MOTOR_ERROR",e);}}
        handler.post(()->{if(current==run){inbox.blockSelected();pause("sensor",false);Log.w("RuxAssistant","MOTION_SENSOR_STOP request="+run.request);}});
    }
    private void launch(JSONObject spec,String request,String command,boolean completionAck)throws Exception {
        validateTrial(spec);
        Run run=new Run(clock.generation,request,command);current=run;
        if(spec.has("audio")) {
            run.audioDone=false;
            try{audio(run,spec.getString("audio"));}catch(Exception e){run.failed=true;run.abort.set(true);run.audioDone=true;clock.pause();Log.e("RuxAssistant","AUDIO_FAILED",e);}
        }
        hardware.execute(()->{
            boolean registered=false;
            SensorCallback callback=new SensorCallback(){
                public void onTapResponse(){sensorStop(run);}public void onDoubleTapResponse(){sensorStop(run);}
                public void onLongPressResponse(){sensorStop(run);}public void onFallBackend(){sensorStop(run);}
                public void onFallForward(){sensorStop(run);}public void onFallRight(){sensorStop(run);}
                public void onFallLeft(){sensorStop(run);}public void onTof(){sensorStop(run);}
            };
            try {
                if(run.abort.get())throw new InterruptedException("Cancelled before run");
                Log.i("RuxAssistant","RUN_START request="+request+" command="+command+" generation="+run.generation+" state="+clock.state);
                String face=spec.optString("face","");if(face.matches("h[0-9]{4}"))robot.robotStartExpression(face);
                if(spec.has("sound"))robot.robotControlSound(spec.getString("sound"));
                if(spec.has("tts"))robot.robotPlayTTs(spec.getString("tts"));
                int light=spec.optInt("light",-1);
                if(light==0)robot.robotCloseAntennaLight();else if(light>0){AntennaLightMessage lamp=new AntennaLightMessage();lamp.set(light);robot.robotAntennaLight(lamp);}
                int motion=spec.optInt("motion",0),motion2=spec.optInt("motion2",0),ears=spec.optInt("ears",0),steps=spec.optInt("steps",1);
                if(motion!=0||motion2!=0||ears!=0) {
                    robot.robotRegisterSensorCallback(callback);registered=true;robot.robotOpenSensor();Thread.sleep(400);
                    MotionSequence.run(motion,motion2,run.abort::get,(code,index)->{
                        synchronized(motorGate) {
                            if(run.abort.get())throw new InterruptedException("Sensor/cancel before motor");
                            robot.robotOpenMotor();
                            if(code!=0){ActionMessage action=new ActionMessage();action.set(code,3,steps);robot.robotActionCommand(action);Log.i("RuxAssistant","MOTION_SENT request="+request+" action="+code+" part="+(index+1));}
                            // Radar and audio play once for the whole pair.
                            if(index==0&&ears!=0&&!run.abort.get()){AntennaMessage antenna=new AntennaMessage();antenna.set(ears,steps,500,spec.optInt("angle",20));robot.robotAntennaMotion(antenna);Log.i("RuxAssistant","EARS_SENT request="+request+" cmd="+ears);}
                        }
                        long end=now()+spec.optInt("duration_ms",3000);
                        while(now()<end&&!run.abort.get())Thread.sleep(50);
                        synchronized(motorGate){robot.robotCloseMotor();Log.i("RuxAssistant","STEP_MOTOR_OFF request="+request+" part="+(index+1));}
                        if(run.abort.get())throw new InterruptedException("Sequence cancelled");
                        if(index==0&&motion!=0&&motion2!=0)Thread.sleep(200);
                    });
                }
                if(run.abort.get())throw new InterruptedException("Run cancelled");
            }catch(Exception e){run.failed=true;Log.w("RuxAssistant","RUN_ABORT request="+request,e);}
            finally {
                synchronized(motorGate){try{robot.robotCloseMotor();Log.i("RuxAssistant","MOTOR_OFF request="+request);}catch(Exception e){run.failed=true;Log.e("RuxAssistant","MOTOR_OFF_FAILED",e);}}
                if(registered)try{robot.robotUnregisterSensor();}catch(Exception e){run.failed=true;Log.e("RuxAssistant","SENSOR_UNREGISTER_FAILED",e);}
                run.done=true;
                handler.post(()->{
                    if(run.failed&&current==run&&clock.active){inbox.blockSelected();pause("run-failure",false);}
                    if(completionAck)completion(run);
                    Log.i("RuxAssistant","RUN_FINISHED request="+request+" failed="+run.failed);
                });
            }
        });
    }
    private void completion(Run run) {
        if(!run.done || (!run.audioDone&&!run.abort.get())){handler.postDelayed(()->completion(run),100);return;}
        reply(run.request,!run.failed&&!run.abort.get(),"command="+run.command+" playback=completed");
    }
    private void audio(Run run,String asset)throws Exception {
        MediaPlayer clip=new MediaPlayer();player=clip;
        clip.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANT).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build());
        try(AssetFileDescriptor fd=getAssets().openFd(asset)){clip.setDataSource(fd.getFileDescriptor(),fd.getStartOffset(),fd.getLength());}
        clip.setOnCompletionListener(p->{p.release();if(player==p)player=null;run.audioDone=true;Log.i("RuxAssistant","AUDIO_DONE request="+run.request);});
        clip.setOnErrorListener((p,what,extra)->{p.release();if(player==p)player=null;run.audioDone=true;run.failed=true;run.abort.set(true);if(current==run){inbox.blockSelected();pause("audio-error",false);}return true;});
        clip.prepare();clip.start();Log.i("RuxAssistant","AUDIO_STARTED request="+run.request+" asset="+asset);
        handler.postDelayed(()->{if(player==clip){clip.release();player=null;run.audioDone=true;run.failed=true;run.abort.set(true);if(current==run){inbox.blockSelected();pause("audio-timeout",false);}}},25000);
    }
    @Override public void onDestroy() {
        destroyed=true;clock.pause();cancelRun();handler.removeCallbacksAndMessages(null);
        hardware.shutdown();
        // Let the serialized finally blocks turn motors off before unbinding SDK.
        new Thread(()->{try{hardware.awaitTermination(6,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();}robot.unbindService();},"RuxCleanup").start();
        super.onDestroy();
    }
}
