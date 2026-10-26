package com.rux.assistant;

import android.app.Activity;
import android.media.MediaPlayer;
import android.media.AudioAttributes;
import android.content.res.AssetFileDescriptor;
import android.content.Context;
import android.content.BroadcastReceiver;
import android.content.Intent;
import org.json.JSONObject;
import com.leitianpai.robotsdk.message.AntennaMessage;
import com.leitianpai.robotsdk.message.AntennaLightMessage;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.Path;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import android.text.TextPaint;
import android.text.StaticLayout;
import android.text.Layout;
import android.text.TextUtils;
import android.view.View;
import android.view.WindowManager;
import android.os.Bundle;
import android.os.Handler;
import android.util.Log;
import android.widget.TextView;
import com.leitianpai.robotsdk.RobotService;
import com.leitianpai.robotsdk.callback.SensorCallback;
import com.leitianpai.robotsdk.message.ActionMessage;
import java.util.concurrent.atomic.AtomicBoolean;

/** Display only: motion and repeat ownership live in ScenarioService. */
public class MainActivity extends Activity {
    private boolean displaying=false;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        receive(getIntent());
    }
    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);setIntent(intent);receive(intent);
    }
    private void receive(Intent intent) {
        if (intent.hasExtra("render_face")) {
            displaying=true;
            setContentView(new PetView(this,intent.getStringExtra("render_face"),
                intent.getStringExtra("render_title"),intent.getStringExtra("render_state"),intent.getStringExtra("render_activity")));
        } else {
            if(!displaying){
                android.content.SharedPreferences saved=getSharedPreferences("display",MODE_PRIVATE);
                setContentView(new PetView(this,saved.getString("face","idle"),saved.getString("title","Codex"),saved.getString("state","idle"),saved.getString("activity","")));displaying=true;
            }
            Intent service=new Intent(this,ScenarioService.class);
            if(intent.getExtras()!=null)service.putExtras(intent.getExtras());
            startForegroundService(service);
        }
    }
    public static class StopReceiver extends BroadcastReceiver {
        @Override public void onReceive(Context context, Intent intent) {
            Intent service=new Intent(context,ScenarioService.class);
            service.putExtra("command","pause");service.putExtra("request",intent.getStringExtra("request"));
            context.startForegroundService(service);
        }
    }
    private static class PetView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final String state;
        private final String statusLabel;
        private final String activity;
        private final long born = android.os.SystemClock.uptimeMillis();
        private final StaticLayout titleLayout;
        PetView(Context context, String state, String title) {
            this(context,state,title,state);
        }
        PetView(Context context, String state, String title, String statusState) {
            this(context,state,title,statusState,"");
        }
        PetView(Context context, String state, String title, String statusState,String activity) {
            super(context);this.activity=activity==null?"":activity;
            this.state = state.equals("working")?"cute_curious":state.equals("attention")?"cute_shy":
                state.equals("completed")?"cute_happy":state.equals("idle")?"cute_sleepy":state.equals("failed")?"cute_sad":state;
            this.statusLabel = statusState.equals("working")?(this.activity.isEmpty()?"Đang suy nghĩ…":"Đang làm cật lực…"):statusState.equals("attention")?"Cần anh một chút":
                statusState.equals("completed")?"Đã trả lời xong":statusState.equals("idle")?"Đang chờ Anh":statusState.equals("failed")?"Có lỗi rồi…":"";
            TextPaint text = new TextPaint(Paint.ANTI_ALIAS_FLAG);
            text.setColor(0xffe7eef2);
            int width = context.getResources().getDisplayMetrics().widthPixels;
            text.setTextSize(width * .044f);
            titleLayout = StaticLayout.Builder.obtain(title.isEmpty() ? "Codex" : title, 0,
                    (title.isEmpty() ? "Codex" : title).length(), text, (int)(width * .70f))
                    .setAlignment(Layout.Alignment.ALIGN_CENTER).setMaxLines(2)
                    .setEllipsize(TextUtils.TruncateAt.END).setIncludePad(false).build();
        }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            canvas.drawColor(0xff05090d);
            float w = getWidth(), h = getHeight();
            if (state.startsWith("cute_")) { drawCute(canvas,w,h); return; }
            int color = state.equals("completed") ? 0xff8aefa4 :
                state.equals("failed") ? 0xffff9a70 : state.equals("attention") ? 0xffffd875 : 0xff83dbe8;
            paint.setColor(color);
            boolean blink = (android.os.SystemClock.uptimeMillis() % 3700) < 130;
            float eyeH = blink ? h * .025f : state.equals("idle") ? h * .035f : h * .18f;
            if (state.equals("working") && !blink) eyeH *= 0.9f + 0.1f * (float)Math.sin(android.os.SystemClock.uptimeMillis()/500.0);
            float y = h * .43f;
            if (state.equals("completed") && !blink) {
                paint.setStyle(Paint.Style.STROKE);
                paint.setStrokeWidth(w * .035f);
                paint.setStrokeCap(Paint.Cap.ROUND);
                canvas.drawArc(w*.19f, y-h*.06f, w*.41f, y+h*.10f, 195, 150, false, paint);
                canvas.drawArc(w*.59f, y-h*.06f, w*.81f, y+h*.10f, 195, 150, false, paint);
                paint.setStyle(Paint.Style.FILL);
            } else {
                canvas.drawRoundRect(w*.18f, y-eyeH/2, w*.42f, y+eyeH/2, w*.06f, w*.06f, paint);
                canvas.drawRoundRect(w*.58f, y-eyeH/2, w*.82f, y+eyeH/2, w*.06f, w*.06f, paint);
            }
            paint.setTextAlign(Paint.Align.CENTER);
            paint.setTextSize(w*.047f);
            String label = state.equals("working") ? "THINKING..." : state.equals("completed") ? "TURN FINISHED" :
                state.equals("attention") ? "NEED YOU" : state.equals("idle") ? "RESTING" : "SOMETHING WENT WRONG";
            canvas.drawText(label, w/2, h*.72f, paint);
            canvas.save();
            canvas.translate((w - titleLayout.getWidth()) / 2, h * .77f);
            titleLayout.draw(canvas);
            canvas.restore();drawActivity(canvas,w,h);
            postInvalidateDelayed(80);
        }
        private void drawActivity(Canvas canvas,float w,float h) {
            if(activity.isEmpty())return;
            TextPaint text=new TextPaint(Paint.ANTI_ALIAS_FLAG);text.setColor(0xffb3c7d5);text.setTextSize(w*.038f);text.setTextAlign(Paint.Align.CENTER);
            String line=TextUtils.ellipsize(activity,text,w*.56f,TextUtils.TruncateAt.END).toString();
            float baseline=Math.min(h*.915f,h*.77f+titleLayout.getHeight()+w*.055f);
            canvas.drawText(line,w/2,baseline,text);
        }
        private void star(Canvas canvas,float x,float y,float r,int color) {
            paint.setStyle(Paint.Style.FILL);paint.setColor(color);
            Path p=new Path();p.moveTo(x,y-r);p.lineTo(x+r*.25f,y-r*.25f);p.lineTo(x+r,y);
            p.lineTo(x+r*.25f,y+r*.25f);p.lineTo(x,y+r);p.lineTo(x-r*.25f,y+r*.25f);
            p.lineTo(x-r,y);p.lineTo(x-r*.25f,y-r*.25f);p.close();canvas.drawPath(p,paint);
        }
        private void heart(Canvas canvas,float x,float y,float r,int color) {
            paint.setColor(color);paint.setStyle(Paint.Style.FILL);
            Path p=new Path();p.moveTo(x,y+r*.9f);
            p.cubicTo(x-r*1.7f,y-r*.15f,x-r*.9f,y-r*1.4f,x,y-r*.55f);
            p.cubicTo(x+r*.9f,y-r*1.4f,x+r*1.7f,y-r*.15f,x,y+r*.9f);
            canvas.drawPath(p,paint);
        }
        private void drawCute(Canvas canvas,float w,float h) {
            long age=android.os.SystemClock.uptimeMillis()-born;
            boolean blink=(age+650)%3900<130;
            float y=h*.3314f+(float)Math.sin(age/650.0)*h*.006f;
            int color=state.equals("cute_sad")?0xfff6b5a7:state.equals("cute_shy")?0xffffb5cf:state.equals("cute_curious")?0xffffda8c:
                state.equals("cute_sleepy")?0xffc8b8f6:state.equals("cute_love")?0xffff8fb6:
                state.equals("cute_wink")?0xffa4e9b9:0xff8de5e3;
            paint.setStyle(Paint.Style.FILL);paint.setColor(0x995f3047);
            canvas.drawOval(w*.12f,h*.555f,w*.24f,h*.605f,paint);
            canvas.drawOval(w*.76f,h*.555f,w*.88f,h*.605f,paint);
            paint.setColor(0xfffa9bb8);
            for(int i=0;i<3;i++) {
                float x=w*(.155f+i*.025f);
                paint.setStrokeWidth(w*.008f);paint.setStrokeCap(Paint.Cap.ROUND);
                canvas.drawLine(x,h*.570f,x-w*.008f,h*.589f,paint);
                canvas.drawLine(w-x,h*.570f,w-x-w*.008f,h*.589f,paint);
            }
            for(int i=0;i<2;i++) {
                float x=w*(i==0?.335f:.665f),rx=w*.13284f,ry=h*.2106f;
                paint.setColor(color);paint.setStyle(Paint.Style.FILL);
                if(state.equals("cute_love")&&!blink) {
                    float heartY=y+h*.0486f, radius=w*.12636f;
                    canvas.save();canvas.scale(1f,1.3f,x,heartY+radius*.9f);
                    heart(canvas,x,heartY,radius,color);canvas.restore();
                }
                else if(blink||state.equals("cute_sleepy")||(state.equals("cute_wink")&&i==0)) {
                    paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(w*.02916f);paint.setStrokeCap(Paint.Cap.ROUND);
                    canvas.drawArc(x-rx,y-h*.04536f,x+rx,y+h*.0729f,195,150,false,paint);
                    paint.setStyle(Paint.Style.FILL);
                } else {
                    if(state.equals("cute_shy"))ry*=.62f;
                    if(state.equals("cute_sad"))ry*=.75f;
                    if(state.equals("cute_curious")&&i==1)ry*=.78f;
                    canvas.drawOval(x-rx,y-ry,x+rx,y+ry,paint);
                    paint.setColor(0xfff7ffff);canvas.drawCircle(x-rx*.28f,y-ry*.32f,w*.03564f,paint);
                    canvas.drawCircle(x+rx*.35f,y+ry*.27f,w*.01458f,paint);
                    if(state.equals("cute_sad")) {
                        paint.setColor(color);paint.setStrokeWidth(w*.008f);
                        canvas.drawLine(x-rx,y-ry-h*(i==0?.02f:.045f),x+rx,y-ry-h*(i==0?.045f:.02f),paint);
                    }
                }
            }
            paint.setColor(color);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(w*.011f);
            paint.setStrokeCap(Paint.Cap.ROUND);
            float my=h*.59f;
            if(state.equals("cute_curious"))canvas.drawOval(w*.48f,my-h*.012f,w*.52f,my+h*.020f,paint);
            else if(state.equals("cute_sad")) {
                Path mouth=new Path();mouth.moveTo(w*.465f,my+h*.02f);
                mouth.quadTo(w*.50f,my-h*.01f,w*.535f,my+h*.02f);canvas.drawPath(mouth,paint);
            } else {
                Path mouth=new Path();mouth.moveTo(w*.46f,my);
                mouth.quadTo(w*.48f,my+h*.035f,w*.50f,my+h*.008f);
                mouth.quadTo(w*.52f,my+h*.035f,w*.54f,my);canvas.drawPath(mouth,paint);
            }
            paint.setStyle(Paint.Style.FILL);
            if(state.equals("cute_sleepy")) {
                paint.setTextSize(w*.055f);paint.setTextAlign(Paint.Align.CENTER);
                canvas.drawText("z",w*.79f,h*.27f+(float)Math.sin(age/900.0)*h*.01f,paint);
                paint.setTextSize(w*.035f);canvas.drawText("z",w*.85f,h*.21f,paint);
            } else if(!state.equals("cute_sad")) {
                star(canvas,w*.18f,h*.27f,w*.018f,color);
                star(canvas,w*.82f,h*.29f,w*.012f,0xfff7e9ba);
            }
            paint.setColor(color);paint.setTextSize(w*(statusLabel.isEmpty()?.036f:.064f));paint.setFakeBoldText(!statusLabel.isEmpty());paint.setTextAlign(Paint.Align.CENTER);
            String label=state.equals("cute_sad")?"Ơ… buồn xíu":state.equals("cute_shy")?"Ngại quá đi…":state.equals("cute_curious")?"Anh gọi em hả?":
                state.equals("cute_sleepy")?"Khò khò…":state.equals("cute_love")?"Thương anh nè":
                state.equals("cute_wink")?"Hi anh!":"Hí hí!";
            if (!statusLabel.isEmpty()) label=statusLabel;
            canvas.drawText(label,w/2,h*(statusLabel.isEmpty()?.69f:.725f),paint);
            paint.setFakeBoldText(false);
            canvas.save();canvas.translate((w-titleLayout.getWidth())/2,h*.77f);titleLayout.draw(canvas);canvas.restore();drawActivity(canvas,w,h);
            postInvalidateDelayed(60);
        }

    }
}
