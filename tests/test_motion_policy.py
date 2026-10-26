"""Exercise the actual device policy on a JVM, with deterministic monotonic time."""
from pathlib import Path
import subprocess
import os
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path(os.environ['JAVA_HOME'])/'bin' if os.environ.get('JAVA_HOME') else Path(shutil.which('javac') or '/usr/bin/javac').parent

class DeviceMotionPolicyTest(unittest.TestCase):
    def test_native_policy_transitions_leases_and_deduplication(self):
        source='''import com.rux.assistant.ScenarioClock;
public class ClockTest {
 static void check(boolean ok,String label){if(!ok)throw new AssertionError(label);}
 public static void main(String[] args){
  ScenarioClock c=new ScenarioClock();
  check(!c.active,"cold start never moves");
  check(c.activate("working","turn1",30,0),"first activation");
  long gen=c.generation;
  check(c.tick(29999)==0,"no early repeat");
  check(c.heartbeat("turn1",15000),"renew correct episode");
  check(!c.heartbeat("stale",20000),"reject stale heartbeat");
  check(c.tick(30000)==1,"repeat on robot at 30s");
  check(c.tick(30001)==0,"no duplicate tick");
  check(!c.activate("working","turn1",30,31000),"duplicate state does not replay");
  check(c.generation==gen && c.due==60000 && c.started==0,"duplicate preserves cadence and cap");
  c.heartbeat("turn1",45000);check(c.tick(60000)==1,"second repeat at 60s");
  check(c.activate("attention","turn1",30,61000),"state transition");
  check(c.tick(90000)==0,"old schedule cancelled");
  c.pause();check(!c.heartbeat("turn1",91000),"heartbeat cannot resume stop");
  check(!c.activate("attention","turn1",30,92000),"same episode cannot rearm stop");
  check(c.tick(96000)==0,"stopped loop stays stopped");
  check(c.activate("working","turn2",30,100000),"new turn can resume");
  check(c.tick(145000)==-1&&!c.active,"lease loss cancels");
  check(!c.heartbeat("turn2",146000),"late heartbeat cannot resume");
  c.activate("working","turn3",30,200000);
  for(long t=215000;t<500000;t+=15000){c.heartbeat("turn3",t);c.tick(t);}
  check(c.heartbeat("turn3",500000),"no five minute heartbeat cap");
  check(c.tick(500000)>=0 && c.state.equals("working"),"long thinking remains working");
  c.activate("completed","turn3",0,501000);
  check(c.tick(510000)==0,"one shot never repeats");
  ScenarioClock fresh=new ScenarioClock();check(!fresh.heartbeat("turn3",0),"restart does not revive episode");
  for(String state:new String[]{"working","attention","failed","idle"}){
   ScenarioClock longRun=new ScenarioClock();longRun.activate(state,"long",30,0);
   for(long t=15000;t<=7200000;t+=15000){check(longRun.heartbeat("long",t),"heartbeat for hours");check(longRun.tick(t)>=0,"non-completed has no timeout");}
   check(longRun.state.equals(state),"state held for hours");
   check(longRun.tick(7250000)==-1,"lost lease stops motion");check(longRun.state.equals(state),"lost lease holds face");
  }
  ScenarioClock done=new ScenarioClock();done.activate("completed","done",0,0);
  check(done.tick(45000)==-1 && done.state.equals("completed"),"lease expiry cannot idle completed early");
  check(done.tick(59999)==0,"completed holds full minute");
  check(done.tick(60000)==-2 && done.state.equals("idle"),"completed rests at sixty seconds");
  check(!done.activate("completed","done",0,61000) && done.state.equals("idle"),"duplicate completed does not restart timer");
  ScenarioClock renewed=new ScenarioClock();renewed.activate("completed","done",0,0);
  renewed.activate("completed","done",0,30000);renewed.heartbeat("done",50000);
  check(renewed.tick(60000)==-2,"heartbeat and duplicate never extend completed timer");
  ScenarioClock changed=new ScenarioClock();changed.activate("completed","a",0,0);changed.activate("working","b",0,59000);
  check(changed.tick(60000)==0 && changed.state.equals("working"),"new state cancels old completion timer");
  System.out.println("device policy checks passed");
 }
}'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'ClockTest.java').write_text(source)
            subprocess.run([str(JAVA/'javac'),'-d',folder,str(ROOT/'android/src/com/rux/assistant/ScenarioClock.java'),str(path/'ClockTest.java')],check=True,capture_output=True)
            result=subprocess.run([str(JAVA/'java'),'-cp',folder,'ClockTest'],check=True,capture_output=True,text=True)
            self.assertIn('checks passed',result.stdout)
