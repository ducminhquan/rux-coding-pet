from pathlib import Path
import subprocess
import tempfile
import unittest
from test_motion_policy import ROOT,JAVA

class MotionSequenceTest(unittest.TestCase):
    def test_native_order_optional_step_and_cancellation(self):
        source='''import com.rux.assistant.MotionSequence;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
public class SequenceTest {
 static void check(boolean ok){if(!ok)throw new AssertionError();}
 public static void main(String[] args)throws Exception {
  List<Integer> sent=new ArrayList<>();
  MotionSequence.run(24,20,()->false,(code,index)->sent.add(code));check(sent.equals(Arrays.asList(24,20)));
  sent.clear();MotionSequence.run(7,0,()->false,(code,index)->sent.add(code));check(sent.equals(Arrays.asList(7)));
  sent.clear();MotionSequence.run(0,20,()->false,(code,index)->sent.add(code));check(sent.equals(Arrays.asList(20)));
  sent.clear();AtomicBoolean stop=new AtomicBoolean();
  try{MotionSequence.run(24,20,stop::get,(code,index)->{sent.add(code);stop.set(true);});throw new AssertionError();}
  catch(InterruptedException expected){}check(sent.equals(Arrays.asList(24)));
  sent.clear();try{MotionSequence.run(24,20,()->true,(code,index)->sent.add(code));throw new AssertionError();}
  catch(InterruptedException expected){}check(sent.isEmpty());
  try{MotionSequence.run(24,20,()->false,(code,index)->{sent.add(code);throw new Exception("hardware failure");});throw new AssertionError();}
  catch(Exception expected){}check(sent.equals(Arrays.asList(24)));
  try{MotionSequence.run(24,81,()->false,(code,index)->{});throw new AssertionError();}catch(IllegalArgumentException expected){}
 }
}'''
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'SequenceTest.java').write_text(source)
            subprocess.run([str(JAVA/'javac'),'-d',folder,str(ROOT/'android/src/com/rux/assistant/MotionSequence.java'),str(p/'SequenceTest.java')],check=True,capture_output=True)
            subprocess.run([str(JAVA/'java'),'-cp',folder,'SequenceTest'],check=True,capture_output=True)
