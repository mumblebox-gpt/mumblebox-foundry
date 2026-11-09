"""Regression checks for GPU refusal and memory budget recovery."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock

path = Path(__file__).parents[1] / "foundry/workflows/ccore_prop"
package = types.ModuleType("ccore_gpu_test")
package.__path__ = [str(path)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location("ccore_gpu_test.gpu", path / "gpu.py")
gpu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpu)


class CcoreGpuTests(unittest.TestCase):
    def test_driver_memory_limits_windows_fit(self):
        output = "projected to use 5353 MiB of device memory vs. 15009 MiB of free device memory"
        result = subprocess.CompletedProcess([], 0, "", output)
        self.assertEqual(gpu.measured_fit(result, 5486), (6377, 5486))
        with self.assertRaisesRegex(ValueError, "verify GPU placement"):
            gpu.measured_fit(subprocess.CompletedProcess([], 0, "", ""), 15009)

    def test_image_reference_cost_is_added_to_each_fit(self):
        output = "projected to use 5353 MiB of device memory vs. 15009 MiB of free device memory"
        result = subprocess.CompletedProcess([], 0, "", output)
        self.assertEqual(gpu.measured_fit(result, 8000, vision=True), (6377 + gpu.VISION_RESERVE_MIB, 8000))
        self.assertGreater(int(gpu.cuda_args("model", 16384, "CUDA0", vision=True)[5]), 20480)

    def test_image_run_requires_the_projector_on_the_selected_cuda_device(self):
        language = ("load_tensors: offloaded 33/33 layers to GPU\n"
                    "llama_kv_cache: CUDA0 KV buffer size = 640.00 MiB\n"
                    "llama_memory_recurrent: CUDA0 RS buffer size = 50.25 MiB\n")
        vision = "clip_ctx: CLIP using CUDA0 backend\nsrv load_model: loaded multimodal model, 'projector'\n"
        gpu.verify_placement(language + vision, "CUDA0", vision=True)
        with self.assertRaisesRegex(ValueError, "vision projector"):
            gpu.verify_placement(language + vision.replace("CLIP using CUDA0", "CLIP using CPU"), "CUDA0", vision=True)

    def test_offers_highest_smaller_fit_and_requires_retry(self):
        measurements = {65536: (6377, 5500), 32768: (5294, 5500), 16384: (4782, 5500)}
        measure = Mock(side_effect=measurements.__getitem__)
        with self.assertRaises(gpu.BudgetDoesNotFit) as rejected:
            gpu.check_budgets(65536, measure, Mock())
        self.assertEqual(rejected.exception.smaller_budget, 32768)
        self.assertEqual([call.args[0] for call in measure.call_args_list], [65536, 32768])

    def test_higher_precision_offers_both_measured_choices(self):
        q8 = {65536: (8077, 7100), 32768: (6994, 7100), 16384: (6482, 7100)}
        q4 = {65536: (6377, 7100)}
        with self.assertRaises(gpu.BudgetDoesNotFit) as rejected:
            gpu.check_budgets(65536, q8.__getitem__, Mock(),
                              model_variant="q8_0", standard_measure=q4.__getitem__)
        self.assertEqual(rejected.exception.fallbacks, [
            {"model_variant": "q4_k_m", "max_tokens": 65536},
            {"model_variant": "q8_0", "max_tokens": 32768},
        ])

    def test_unavailable_standard_does_not_create_a_fallback(self):
        with self.assertRaises(gpu.BudgetDoesNotFit) as rejected:
            gpu.check_budgets(16384, lambda _: (6482, 5100), Mock(),
                              model_variant="q8_0", standard_measure=lambda _: None)
        self.assertEqual(rejected.exception.fallbacks, [])

    def test_checks_a_smaller_standard_budget_when_same_budget_will_not_fit(self):
        q4 = {65536: (6377, 5400), 32768: (5294, 5400), 16384: (4782, 5400)}
        with self.assertRaises(gpu.BudgetDoesNotFit) as rejected:
            gpu.check_budgets(65536, lambda _: (6482, 5400), Mock(),
                              model_variant="q8_0", standard_measure=q4.__getitem__)
        self.assertEqual(rejected.exception.fallbacks, [{"model_variant": "q4_k_m", "max_tokens": 32768}])

    def test_no_offer_if_nothing_fits(self):
        with self.assertRaises(gpu.BudgetDoesNotFit) as rejected:
            gpu.check_budgets(32768, lambda _: (5294, 4500), Mock())
        self.assertIsNone(rejected.exception.smaller_budget)
        self.assertIn("Free GPU memory", str(rejected.exception))

    def test_requires_all_layers_and_both_caches_on_selected_cuda_gpu(self):
        startup = ("load_tensors: offloaded 33/33 layers to GPU\n"
                   "llama_kv_cache: CUDA0 KV buffer size = 640.00 MiB\n"
                   "llama_memory_recurrent: CUDA0 RS buffer size = 50.25 MiB\n")
        gpu.verify_placement(startup, "CUDA0")
        for bad in (startup.replace("33/33", "31/33"), startup.replace("CUDA0 KV", "CPU KV"),
                    startup + "llama_kv_cache: CPU KV buffer size = 10.00 MiB\n", ""):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "keep all model layers"):
                gpu.verify_placement(bad, "CUDA0")


if __name__ == "__main__":
    unittest.main()
