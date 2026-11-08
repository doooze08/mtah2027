"""Aggregate ball-position gaps using tracking coordinates only.

    python -m experiments.20261108_ball_gaps.ball_gaps --dataset <simulation_dataset_id>
    python -m experiments.20261108_ball_gaps.ball_gaps --data-dir /path/to/data

No frame records, clip identifiers, labels or tracking timestamps are exported.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from observations.schema import SLOTS


def _histogram(values, cutoffs):
    counts = np.bincount(np.searchsorted(cutoffs, values, side="right"),
                         minlength=len(cutoffs) + 1)
    names = (["<{}".format(cutoffs[0])]
             + ["[{}, {})".format(a, b) for a, b in zip(cutoffs[:-1], cutoffs[1:])]
             + [">={}".format(cutoffs[-1])])
    return {name: {"count": int(count),
                   "fraction": float(count / len(values)) if len(values) else 0.0}
            for name, count in zip(names, counts)}


def _distribution(values, cutoffs=None):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    result = {"count": len(finite), "unavailable_count": len(values) - len(finite)}
    for name, percentile in (("p10", 10), ("p50", 50), ("p90", 90), ("p99", 99)):
        result[name] = float(np.percentile(finite, percentile)) if len(finite) else None
    result["max"] = float(finite.max()) if len(finite) else None
    if cutoffs is not None:
        result["bins"] = _histogram(finite, cutoffs)
    return result


def summarize(clips):
    """Summarize an iterable of (observations, metadata), never joining clip boundaries."""
    lengths, durations, jumps, player_counts = [], [], [], []
    contexts = {side: {key: [] for key in (
        "speed_m_s", "nearest_player_m", "touchline_m", "goal_line_m")}
        for side in ("before", "after")}
    total_frames = missing_frames = clip_count = left = right = complete = 0
    for observations, metadata in clips:
        clip_count += 1
        n = len(observations)
        total_frames += n
        scale = np.array([metadata["pitch_length"], metadata["pitch_width"]])
        ball = observations[["ball_x", "ball_y"]].to_numpy(dtype=float) * scale
        missing = np.isnan(ball).any(axis=1)
        missing_frames += int(missing.sum())
        players = np.stack([observations[[s + "_x", s + "_y"]].to_numpy(dtype=float)
                            for s in SLOTS], axis=1) * scale
        visible = ~np.isnan(players).any(axis=2)
        player_counts.extend(visible[missing].sum(axis=1).tolist())
        edges = np.flatnonzero(np.diff(np.r_[False, missing, False]))
        for start, stop in zip(edges[::2], edges[1::2]):
            length = int(stop - start)
            lengths.append(length)
            durations.append(length / metadata["fps"])
            left += int(start == 0)
            right += int(stop == n)
            bounded = start > 0 and stop < n
            complete += int(bounded)
            jumps.append(float(np.linalg.norm(ball[stop] - ball[start - 1]))
                         if bounded else None)
            for side, index, neighbor in (("before", start - 1, start - 2),
                                           ("after", stop, stop + 1)):
                context = contexts[side]
                if not 0 <= index < n:
                    for values in context.values():
                        values.append(None)
                    continue
                point = ball[index]
                speed = (np.linalg.norm(point - ball[neighbor]) * metadata["fps"]
                         if 0 <= neighbor < n and not missing[neighbor] else None)
                distances = np.linalg.norm(players[index, visible[index]] - point, axis=1)
                context["speed_m_s"].append(speed)
                context["nearest_player_m"].append(float(distances.min())
                                                    if len(distances) else None)
                context["touchline_m"].append(float(min(point[1], scale[1] - point[1])))
                context["goal_line_m"].append(float(min(point[0], scale[0] - point[0])))

    # The 30 s endpoint belongs to the fourth bin, as specified in the duration table.
    duration_bins = np.searchsorted([0.2, 1, 5, 30], durations, side="right")
    duration_bins[np.asarray(durations) == 30] = 3
    bins = {}
    for index, name in enumerate(("<0.2", "[0.2, 1)", "[1, 5)", "[5, 30]", ">30")):
        selected = duration_bins == index
        frames = int(np.asarray(lengths, dtype=int)[selected].sum())
        bins[name] = {"gap_count": int(selected.sum()), "missing_frames": frames,
                      "fraction_of_missing_frames": frames / missing_frames if missing_frames else 0.0,
                      "fraction_of_all_frames": frames / total_frames if total_frames else 0.0}
    cutoffs = {"speed_m_s": [1, 3, 7, 15, 30], "nearest_player_m": [1, 2, 5, 10, 20],
               "touchline_m": [0, 1, 3, 5, 10, 20], "goal_line_m": [0, 1, 3, 5, 10, 20]}
    return {
        "clip_count": clip_count, "total_frames": total_frames,
        "missing_frames": missing_frames,
        "missing_fraction": missing_frames / total_frames if total_frames else 0.0,
        "gap_count": len(lengths), "complete_gap_count": complete,
        "left_censored_gap_count": left, "right_censored_gap_count": right,
        "censored_gap_count": len(lengths) - complete,
        "gap_length_frames": _distribution(lengths),
        "gap_length_s": _distribution(durations), "duration_bins_s": bins,
        "context": {side: {key: _distribution(values, cutoffs[key])
                            for key, values in measurements.items()}
                    for side, measurements in contexts.items()},
        "reappearance_jump_m": _distribution(jumps, [1, 5, 10, 25, 50]),
        "visible_players_during_gaps": {
            **_distribution(player_counts),
            "counts": {str(k): int(v) for k, v in enumerate(
                np.bincount(player_counts, minlength=len(SLOTS) + 1))}},
    }


def markdown(report):
    """Render a short Chinese summary; full histograms remain in the aggregate JSON."""
    def number(value):
        return "—" if value is None else "{:.3g}".format(value)

    def percentiles(stats):
        return " / ".join(number(stats[key]) for key in ("p10", "p50", "p90", "p99", "max"))

    lines = ["# 球位置缺失统计", "",
             "片段数 {}；总帧数 {}；缺球 {} 帧（{:.2%}）；缺失段 {}。".format(
                 report["clip_count"], report["total_frames"], report["missing_frames"],
                 report["missing_fraction"], report["gap_count"]),
             "长度 P10 / 中位数 / P90 / P99 / 最长：{} 帧；{} s。".format(
                 percentiles(report["gap_length_frames"]), percentiles(report["gap_length_s"])),
             "首端截断 {} 段，尾端截断 {} 段；截断合计 {} 段（可能重叠）；完整 {} 段。".format(
                 report["left_censored_gap_count"], report["right_censored_gap_count"],
                 report["censored_gap_count"], report["complete_gap_count"]), "",
             "| 缺失时长（s） | 段数 | 缺球帧数 | 占全部缺球帧 | 占全部帧 |",
             "|---|---:|---:|---:|---:|"]
    for name, stats in report["duration_bins_s"].items():
        lines.append("| {} | {} | {} | {:.2%} | {:.2%} |".format(
            name, stats["gap_count"], stats["missing_frames"],
            stats["fraction_of_missing_frames"], stats["fraction_of_all_frames"]))
    lines += ["", "| 边界上下文 | 消失前 P50 / P90（可算 / 不可算） | 恢复后 P50 / P90（可算 / 不可算） |",
              "|---|---|---|"]
    for key, title in (("speed_m_s", "球速（m/s）"), ("nearest_player_m", "最近球员（m）"),
                        ("touchline_m", "最近边线（m）"), ("goal_line_m", "最近底线（m）")):
        cells = []
        for side in ("before", "after"):
            stats = report["context"][side][key]
            cells.append("{} / {}（{} / {}）".format(
                number(stats["p50"]), number(stats["p90"]), stats["count"], stats["unavailable_count"]))
        lines.append("| {} | {} | {} |".format(title, *cells))
    jump = report["reappearance_jump_m"]
    players = report["visible_players_during_gaps"]
    lines += ["", "消失至重现直线距离 P10 / P50 / P90 / P99 / 最大：{} m；可算 {}，不可算 {}。".format(
        percentiles(jump), jump["count"], jump["unavailable_count"]),
        "缺球时可见球员数 P10 / P50 / P90 / P99 / 最大：{}。数量:帧数 = {}。".format(
            percentiles(players), "；".join("{}:{}".format(k, v)
                                              for k, v in players["counts"].items() if v) or "无"), "",
        "口径：任一球坐标 NaN 即缺球；片段间不连接。速度只用同侧相邻可见帧，不跨缺失段。",
        "每段缺失每侧至多计一个上下文样本，等权汇总；缺少端点或相邻观测计为不可算。边界距离场内为正、场外为负。",
        "截断段长度为已观测部分；跳变距离不是实际行程。可见球员要求 x/y 均非 NaN，未用槽位也计入 46 槽位基数。",
        "JSON 保留完整分档，分档比例以可计算样本为分母，空分布为 null、比例为 0；报告不含帧号或具体时刻。", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data-dir", help="Tactical data root; omit for the configured default")
    source.add_argument("--dataset", help="Simulation dataset ID; reads observations and metadata only")
    parser.add_argument("--out", type=Path, help="New output directory; never overwrites a prior report")
    args = parser.parse_args(argv)
    out = args.out or Path("outputs/ball_gaps") / (args.dataset or "tactical")
    out.mkdir(parents=True, exist_ok=False)
    if args.dataset:
        from simulation.core.io import dataset_dir, load_clips

        clips = ((obs, meta) for _, obs, meta in load_clips(dataset_dir(args.dataset)))
    else:
        from observations.atd import load_tactical

        clips = [load_tactical(args.data_dir)]
    report = summarize(clips)
    (out / "statistics.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    (out / "summary.md").write_text(markdown(report))
    print("wrote {} and {}".format(out / "statistics.json", out / "summary.md"))


if __name__ == "__main__":
    main()
