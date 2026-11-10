import sys
from pathlib import Path
import unittest

import torch

sys.path.insert(0, str(Path(__file__).parents[1] / 'pipeline_workers'))
from smd_texture import fuse_texture_adapter, texture_grid


class SmdTextureTests(unittest.TestCase):
    def test_released_four_step_shifted_grid(self):
        torch.testing.assert_close(texture_grid(), torch.tensor(
            [1.0, .9, .75, .5, 0.0], dtype=torch.float64))

    def test_merge_uses_fp32_delta_and_bfloat16_weight(self):
        layer = torch.nn.Linear(2, 2, bias=False, dtype=torch.bfloat16)
        layer.weight.data.fill_(0.25)
        a = torch.tensor([[2, 4]], dtype=torch.bfloat16)
        b = torch.tensor([[3], [5]], dtype=torch.bfloat16)
        fuse_texture_adapter(torch.nn.Sequential(layer), {'0.lora_A': a, '0.lora_B': b}, 1.0)
        torch.testing.assert_close(layer.weight, (b.float() @ a.float() + .25).bfloat16())

    def test_unmatched_tensor_does_not_change_any_weight(self):
        model = torch.nn.Sequential(torch.nn.Linear(2, 2, bias=False))
        original = model[0].weight.detach().clone()
        a, b = torch.ones(1, 2), torch.ones(2, 1)
        with self.assertRaisesRegex(ValueError, 'adapter tensor'):
            fuse_texture_adapter(model, {'0.lora_A': a, '0.lora_B': b, 'bad': b}, 1.0)
        torch.testing.assert_close(model[0].weight, original)


if __name__ == '__main__':
    unittest.main()
