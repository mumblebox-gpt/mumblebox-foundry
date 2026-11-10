"""Annealed matching as in PyTorchEMD (Haoqiang Fan and Kaichun Mo)."""
import torch


def distances(points, guide):
    return torch.cdist(points.float(), guide.float(), compute_mode="donot_use_mm_for_euclid_dist")


def one_way_chamfer(points, guide):
    return distances(points, guide).square().amin(dim=0).mean()


def emd(points, guide):
    cost = distances(points, guide)
    with torch.no_grad():
        squared = cost.detach().square()
        n, m = squared.shape
        left = squared.new_full((n,), max(1, m // n))
        right = squared.new_full((m,), max(1, n // m))
        coupling = torch.zeros_like(squared)
        for level in range(7, -3, -1):
            similarity = torch.ones_like(squared) if level == -2 else (-4.0 ** level * squared).exp()
            source = left / ((similarity @ right) + 1e-9)
            demand = (source @ similarity) * right
            target = (right / (demand + 1e-9)).clamp(max=1) * right
            right = (right - demand).clamp(min=0)
            moved = similarity.mul_(source[:, None]).mul_(target[None, :])
            coupling.add_(moved)
            left = (left - moved.sum(dim=1)).clamp(min=0)
    return (cost * coupling).sum()

