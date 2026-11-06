import unittest
from backend.platform.drowning_gate import DrowningGate

class GateTests(unittest.TestCase):
    def test_only_fifteenth_distinct_positive_frame_confirms(self):
        gate=DrowningGate()
        for frame in range(1,16):
            result=gate.observe(1,frame,float(frame),'DROWNING',0.8)
            self.assertEqual(result['confirmed'],frame==15)
        self.assertTrue(result['new_confirmation'])
        self.assertFalse(gate.observe(1,16,16.,'DROWNING',0.9)['new_confirmation'])

    def test_replays_and_out_of_order_do_not_count(self):
        gate=DrowningGate();gate.observe(1,1,1.,'DROWNING',0.9)
        self.assertIsNone(gate.observe(1,1,2.,'DROWNING',0.9))
        self.assertIsNone(gate.observe(1,2,0.,'DROWNING',0.9))
        self.assertEqual(gate.observe(1,2,2.,'DROWNING',0.9)['consecutive_frames'],2)

    def test_invalid_score_or_state_breaks_streak(self):
        for state,score in [('SWIMMING',1.),('UNCLEAR',1.),('DROWNING',None),('DROWNING',0.79),('DROWNING',float('nan')),('DROWNING',1.1)]:
            gate=DrowningGate();gate.observe(1,1,1.,'DROWNING',0.9)
            self.assertEqual(gate.observe(1,2,2.,state,score)['consecutive_frames'],0)

    def test_tracks_loss_and_observation_gap_reset(self):
        gate=DrowningGate();gate.observe(1,1,1.,'DROWNING',0.9)
        self.assertEqual(gate.observe(2,2,2.,'DROWNING',0.9)['consecutive_frames'],1)
        gate.retain({2})
        self.assertEqual(gate.observe(1,3,3.,'DROWNING',0.9)['consecutive_frames'],1)
        self.assertEqual(gate.observe(1,4,30.,'DROWNING',0.9)['consecutive_frames'],1)
