package com.rux.assistant;

import java.util.function.BooleanSupplier;

/** Runs the optional return action only after the first bounded step completes. */
public final class MotionSequence {
    public interface Step { void execute(int code,int index)throws Exception; }
    public static void run(int first,int second,BooleanSupplier cancelled,Step step)throws Exception {
        if(first<0||first>80||second<0||second>80)throw new IllegalArgumentException("Motion bounds");
        int[] codes=second==0?new int[]{first}:first==0?new int[]{second}:new int[]{first,second};
        for(int i=0;i<codes.length;i++) {
            if(cancelled.getAsBoolean())throw new InterruptedException("Sequence cancelled");
            step.execute(codes[i],i);
        }
    }
}
