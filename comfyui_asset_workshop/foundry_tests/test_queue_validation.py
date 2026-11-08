import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from foundry.queue_validation import rejection
class QueueValidation(unittest.TestCase):
    def test_partial_http_success_is_a_failure(self):
        self.assertIn('382',rejection({'prompt_id':'p','node_errors':{'382':{'errors':['missing model']}}},200))
    def test_complete_valid_stage_is_accepted(self):self.assertIsNone(rejection({'prompt_id':'p','node_errors':{}},200))
    def test_full_rejection_is_reported(self):self.assertIsNotNone(rejection({'error':{'type':'invalid_prompt'}},400))
