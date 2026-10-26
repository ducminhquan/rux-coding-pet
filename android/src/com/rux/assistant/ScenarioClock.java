package com.rux.assistant;

/** Device-owned motion lease and independent completed-face timer. */
public final class ScenarioClock {
    public static final long LEASE_MS=45000, COMPLETED_MS=60000;
    public boolean active;
    public String state="idle", context="";
    private String episodeState="idle";
    private long completedAt=Long.MAX_VALUE;
    public long generation, started, due, lease;
    public int repeat;
    public boolean activate(String state,String context,int repeat,long now) {
        // A duplicate must not replay or restart the one-minute completed timer.
        if(episodeState.equals(state)&&this.context.equals(context)&&generation>0){
            if(active&&now<lease)lease=now+LEASE_MS;
            return false;
        }
        generation++;this.state=state;episodeState=state;this.context=context;this.repeat=repeat;
        active=true;started=now;due=repeat>0?now+repeat*1000L:Long.MAX_VALUE;
        completedAt=state.equals("completed")?now+COMPLETED_MS:Long.MAX_VALUE;
        lease=now+LEASE_MS;return true;
    }
    public boolean heartbeat(String context,long now) {
        if(!active||!this.context.equals(context)||now>=lease)return false;
        lease=now+LEASE_MS;return true;
    }
    /** -2 completed -> idle; -1 cancel motion only; 0 wait; 1 one repeat. */
    public int tick(long now) {
        if(now>=completedAt){completedAt=Long.MAX_VALUE;state="idle";pause();return -2;}
        if(!active)return 0;
        if(now>=lease){pause();return -1;}
        if(repeat>0&&now>=due){due=now+repeat*1000L;return 1;}
        return 0;
    }
    public void pause(){active=false;generation++;}
}
