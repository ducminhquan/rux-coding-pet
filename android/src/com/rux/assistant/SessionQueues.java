package com.rux.assistant;

import java.util.LinkedHashMap;
import java.util.Map;

/** Robot-side arbitration. Each source/session has its own sequenced state stream.
 * Old states coalesce, so switching chats never replays obsolete movements. */
public final class SessionQueues {
    public static final class Entry {
        public String source, session, turn, state, title, activity="";
        public long sequence, lease, updated;
        public boolean blocked, dirty=true, quiet, noMotion;
        public String key(){return source+":"+session;}
        public String context(){return source+":"+session.length()+":"+session+":"+turn.length()+":"+turn+":"+state;}
        public boolean terminal(){return state.equals("completed")||state.equals("idle");}
    }
    private final LinkedHashMap<String,Entry> entries=new LinkedHashMap<>();
    private String selected;
    public boolean held;
    public Entry get(String source,String session){return entries.get(source+":"+session);}
    public java.util.Collection<Entry> entries(){return entries.values();}
    public Entry selected(){return entries.get(selected);}
    public Entry accept(String source,String session,String turn,String state,String title,long sequence,boolean quiet,boolean noMotion,long now) {
        return accept(source,session,turn,state,title,"",sequence,quiet,noMotion,now);
    }
    public Entry accept(String source,String session,String turn,String state,String title,String activity,long sequence,boolean quiet,boolean noMotion,long now) {
        if(!source.matches("codex|claude|kiro")||!session.matches("[a-zA-Z0-9._:-]{1,200}")||turn.length()>200||sequence<1||
            !state.matches("working|attention|completed|idle|failed"))throw new IllegalArgumentException("Invalid queue envelope");
        String key=source+":"+session;Entry e=entries.get(key);
        if(e!=null&&sequence<=e.sequence)return null;
        if(e==null) {
            entries.entrySet().removeIf(item->item.getValue().lease<=now&&!item.getKey().equals(selected));
            if(entries.size()>=64)throw new IllegalStateException("Session inbox full");
            e=new Entry();e.source=source;e.session=session;e.turn="";e.state="idle";entries.put(key,e);
        }
        boolean changed=!turn.equals(e.turn)||!state.equals(e.state);
        if(changed){e.blocked=false;e.dirty=true;}
        else if(!title.equals(e.title)||!activity.equals(e.activity))e.dirty=true;
        e.turn=turn;e.state=state;e.title=title;e.activity=activity;e.sequence=sequence;e.quiet=quiet;e.noMotion=noMotion;
        e.lease=now+ScenarioClock.LEASE_MS;e.updated=now;return e;
    }
    public boolean heartbeat(String source,String session,long sequence,long now) {
        Entry e=get(source,session);
        if(e==null||e.blocked||e.lease<=now||sequence<=e.sequence)return false;
        e.sequence=sequence;e.lease=now+ScenarioClock.LEASE_MS;return true;
    }
    public Entry choose(long now,boolean finished) {
        if(held)return null;
        // Bootstrap once. After that, only explicit selection changes the chat.
        // Keep the selected key even if terminal, blocked or disconnected.
        if(selected!=null){
            Entry current=selected();
            return current!=null&&!current.blocked&&current.lease>now?current:null;
        }
        for(Entry e:entries.values())if(!e.blocked&&e.lease>now&&!e.terminal()){
            selected=e.key();e.dirty=true;return e;
        }
        return null;
    }
    public Entry select(String source,String session,long now) {
        Entry e=get(source,session);
        if(held||e==null||e.blocked||e.lease<=now)throw new IllegalArgumentException("Queue unavailable");
        selected=e.key();e.dirty=true;return e;
    }
    public void blockSelected(){Entry e=selected();if(e!=null)e.blocked=true;}
    public void stopAll(){for(Entry e:entries.values())e.blocked=true;}
}
