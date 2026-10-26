package com.rux.assistant;

import android.content.Context;
import android.util.AtomicFile;
import org.json.JSONObject;
import org.json.JSONArray;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/** Validates before atomic replacement; interrupted updates preserve the old file. */
final class ScenarioStore {
    static final String[] STATES={"working","attention","completed","idle","failed"};
    final Context context;
    final AtomicFile file;
    JSONObject data;
    String revision;
    ScenarioStore(Context context)throws Exception {
        this.context=context;file=new AtomicFile(new File(context.getFilesDir(),"scenarios.json"));
        JSONObject bundled=new JSONObject(read(context.getAssets().open("scenarios.json")));
        validate(bundled);data=bundled;
        if(file.getBaseFile().exists()) {
            // A corrupt private file fails closed: no motion is active at startup.
            data=new JSONObject(read(file.openRead()));validate(data);
        } else save(bundled);
        revision=hash(data.toString());
    }
    static String read(InputStream in)throws Exception {
        try(InputStream stream=in;ByteArrayOutputStream out=new ByteArrayOutputStream()) {
            byte[] bytes=new byte[4096];int n;
            while((n=stream.read(bytes))!=-1){out.write(bytes,0,n);if(out.size()>16384)throw new IllegalArgumentException("Config too large");}
            return new String(out.toByteArray(),StandardCharsets.UTF_8);
        }
    }
    static String hash(String value)throws Exception {
        byte[] bytes=MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder s=new StringBuilder();for(byte b:bytes)s.append(String.format("%02x",b&255));return s.toString().substring(0,16);
    }
    static void keys(JSONObject obj,String... names)throws Exception {
        Set<String> allowed=new HashSet<>(Arrays.asList(names));
        if(obj.length()!=allowed.size())throw new IllegalArgumentException("Config keys");
        java.util.Iterator<String> it=obj.keys();while(it.hasNext())if(!allowed.contains(it.next()))throw new IllegalArgumentException("Unknown config field");
    }
    static int number(JSONObject obj,String key,int min,int max)throws Exception {
        Object v=obj.get(key);
        if(!(v instanceof Integer) && !(v instanceof Long))throw new IllegalArgumentException("Expected integer: "+key);
        long n=((Number)v).longValue();if(n<min||n>max)throw new IllegalArgumentException("Bounds: "+key);return (int)n;
    }
    void validate(JSONObject config)throws Exception {
        keys(config,"version","voice","states");number(config,"version",1,1);
        String voice=config.getString("voice");
        JSONArray voices=new JSONArray(read(context.getAssets().open("voices.json")));
        boolean found=false;for(int i=0;i<voices.length();i++)if(voices.getJSONObject(i).getString("id").equals(voice))found=true;
        if(!found)throw new IllegalArgumentException("Unknown voice");
        JSONObject states=config.getJSONObject("states");keys(states,STATES);
        for(String state:STATES) {
            JSONObject spec=states.getJSONObject(state);
            if(!spec.has("motion2"))spec.put("motion2",0);
            keys(spec,"face","motion","motion2","ears","angle","repeat");
            String face=spec.getString("face");
            if(!face.matches("h[0-9]{4}|working|attention|completed|idle|failed|cute_happy|cute_shy|cute_curious|cute_sleepy|cute_love|cute_wink|cute_sad"))throw new IllegalArgumentException("Unknown face");
            number(spec,"motion",0,80);number(spec,"motion2",0,80);number(spec,"ears",0,2);number(spec,"angle",1,45);
            int repeat=number(spec,"repeat",0,300);if(repeat>0&&repeat<20)throw new IllegalArgumentException("Repeat below 20s");
        }
        for(String state:new String[]{"attention","completed"}) {
            try(InputStream in=context.getAssets().open("voice-"+voice+"-"+state+".wav")){}
        }
    }
    void save(JSONObject config)throws Exception {
        validate(config);String next=hash(config.toString());FileOutputStream out=null;
        try{out=file.startWrite();out.write(config.toString().getBytes(StandardCharsets.UTF_8));file.finishWrite(out);}
        catch(Exception e){if(out!=null)file.failWrite(out);throw e;}
        data=config;revision=next;
    }
    JSONObject preset(String state)throws Exception{return data.getJSONObject("states").getJSONObject(state);}
}
