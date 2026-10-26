from pathlib import Path
import subprocess
import tempfile
import unittest
from test_motion_policy import ROOT,JAVA

class RobotQueueTest(unittest.TestCase):
    def test_robot_selects_sessions_and_rejects_stale_or_blocked_streams(self):
        source='''import com.rux.assistant.SessionQueues;
public class InboxTest {
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
 public static void main(String[] args){
  SessionQueues q=new SessionQueues();
  SessionQueues.Entry a=q.accept("codex","a","t1","working","A",1,true,false,0);
  check(q.choose(0,true)==a,"first queue selected");a.dirty=false;
  SessionQueues.Entry b=q.accept("claude","b","t2","working","B",1,true,false,100);
  check(q.choose(100,true)==a,"busy chat sticky, no host priority");
  q.accept("claude","b","t2","attention","B",2,true,false,200);
  check(q.accept("claude","b","t1","completed","old",1,true,false,250)==null,"stale sequence ignored");
  check(b.state.equals("attention"),"pending states coalesce");
  q.accept("codex","a","t1","completed","A",2,true,false,300);
  check(q.choose(300,true)==a,"terminal state first delivered");a.dirty=false;
  check(q.choose(301,false)==a,"wait for old motor/audio cleanup");
  check(q.choose(302,true)==a,"completion never hands off to B");
  check(q.select("claude","b",303)==b,"explicit selection changes chat");b.dirty=false;
  check(q.heartbeat("codex","a",3,400),"non-selected heartbeat renews its own lease");
  check(!q.heartbeat("codex","a",2,401),"old heartbeat rejected");
  q.stopAll();check(q.choose(500,true)==null,"stop blocks all current episodes");
  check(!q.heartbeat("claude","b",3,501),"heartbeat cannot undo stop");
  q.accept("claude","b","t2","attention","B",4,true,false,502);
  check(q.choose(502,true)==null,"same episode cannot undo stop");
  q.accept("claude","b","t3","working","B",5,true,false,600);
  check(q.choose(600,true)==b,"selected chat new turn allowed");b.dirty=false;
  q.held=true;check(q.choose(700,true)==null,"manual hold prevents selection");q.held=false;
  check(q.choose(46000,true)==null,"expired queue not replayed");
  SessionQueues sticky=new SessionQueues();
  SessionQueues.Entry first=sticky.accept("codex","first","t","working","A",1,true,false,0);sticky.choose(0,true);first.dirty=false;
  sticky.accept("kiro","waiting","t","working","B",1,true,false,40000);
  check(sticky.choose(46000,true)==null,"expired A never automatically selects live B");
  check(sticky.selected()==first,"selection survives disconnection");
  sticky.accept("kiro","waiting","next","working","B",2,true,false,47000);
  check(sticky.choose(47000,true)==null,"new prompt in B still cannot steal selection");
  SessionQueues collision=new SessionQueues();
  SessionQueues.Entry x=collision.accept("kiro","a:b","c","working","X",1,true,false,0);
  SessionQueues.Entry y=collision.accept("kiro","a","b:c","working","Y",1,true,false,0);
  check(!x.context().equals(y.context()),"session/turn boundaries cannot collide");
  SessionQueues notes=new SessionQueues();
  SessionQueues.Entry n=notes.accept("codex","note","t","working","N","Reading app.js",1,true,false,0);
  notes.choose(0,true);n.dirty=false;String context=n.context();
  notes.accept("codex","note","t","working","N","Editing app.js",2,true,false,10);
  check(n.dirty && n.context().equals(context),"activity updates do not create a new motion episode");
  notes.accept("claude","other","t","working","O","Reading other.js",1,true,false,20);
  check(notes.choose(20,true)==n && n.activity.equals("Editing app.js"),"other chat activity cannot steal display");
  SessionQueues fresh=new SessionQueues();check(fresh.choose(0,true)==null,"restart has no active state");
  try{q.accept("unknown","x","t","working","X",1,true,false,0);throw new AssertionError();}catch(IllegalArgumentException expected){}
 }
}'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'InboxTest.java').write_text(source)
            subprocess.run([str(JAVA/'javac'),'-d',folder,str(ROOT/'android/src/com/rux/assistant/ScenarioClock.java'),str(ROOT/'android/src/com/rux/assistant/SessionQueues.java'),str(p/'InboxTest.java')],check=True,capture_output=True)
            subprocess.run([str(JAVA/'java'),'-cp',folder,'InboxTest'],check=True,capture_output=True)
