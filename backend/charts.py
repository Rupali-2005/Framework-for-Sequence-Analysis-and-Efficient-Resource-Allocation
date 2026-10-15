import base64
from io import BytesIO

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure


METRICS = (
    ("Avg. waiting", "average_waiting_time"),
    ("Avg. turnaround", "average_turnaround_time"),
    ("Makespan", "makespan"),
)


def dashboard_chart(results: dict[str, dict]) -> str:
    algorithms = list(results)
    figure = Figure(figsize=(11, 5), facecolor="#0b1220", layout="constrained")
    axis = figure.subplots()
    figure.suptitle(
        "Scheduling metrics comparison",
        color="#e9eef7",
        fontsize=16,
        fontweight="bold",
    )

    positions = list(range(len(METRICS)))
    bar_width = 0.8 / max(len(algorithms), 1)
    palette = ("#4f9cf9", "#55d6be", "#f6bd60", "#f28482", "#a78bfa")

    for index, algorithm in enumerate(algorithms):
        values = [results[algorithm][key] for _, key in METRICS]
        offsets = [
            position - 0.4 + bar_width * (index + 0.5)
            for position in positions
        ]
        bars = axis.bar(
            offsets,
            values,
            width=bar_width,
            label=algorithm,
            color=palette[index % len(palette)],
        )
        axis.bar_label(
            bars,
            padding=2,
            color="#e9eef7",
            fontsize=7,
            fmt="%.2f",
        )

    axis.set_xticks(positions, [title for title, _ in METRICS])
    axis.set_ylabel("Time units", color="#9aacc5")
    axis.legend(
        facecolor="#121d30",
        edgecolor="#263956",
        labelcolor="#e9eef7",
        ncols=min(len(algorithms), 5),
    )
    _style_axis(axis)

    canvas = FigureCanvasAgg(figure)
    output = BytesIO()
    canvas.print_png(output)
    image = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{image}"


def _style_axis(axis) -> None:
    axis.set_facecolor("#0c1626")
    axis.tick_params(colors="#b9c6da", labelrotation=15)
    axis.grid(axis="y", color="#263956", alpha=0.8)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_color("#263956")
