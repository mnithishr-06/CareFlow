"""Discover and export a clinical pathway Petri net using pm4py."""

import argparse
from collections import Counter
from pathlib import Path
import shutil
import subprocess

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd

from data_loader import load_event_log


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "data" / "raw" / "clinical_events.csv"
DEFAULT_MODEL_OUTPUT = REPOSITORY_ROOT / "models" / "clinical_petri_net.pnml"
DEFAULT_VISUAL_OUTPUT = (
    REPOSITORY_ROOT / "visuals" / "petri_net_discovered.png"
)


def format_event_log(events):
    """Return a DataFrame with pm4py's standard event-log column names."""
    event_log = events.rename(
        columns={
            "case_id": "case:concept:name",
            "event_name": "concept:name",
            "event_timestamp": "time:timestamp",
        }
    )
    return event_log[
        ["case:concept:name", "concept:name", "time:timestamp"]
    ].copy()


def _petri_node_label(node, initial_marking, final_marking):
    """Label places with marking tokens and transitions with activity names."""
    if hasattr(node, "name") and not hasattr(node, "label"):
        tokens = []
        if initial_marking.get(node, 0):
            tokens.append(f"start:{initial_marking[node]}")
        if final_marking.get(node, 0):
            tokens.append(f"end:{final_marking[node]}")
        return ", ".join(tokens)
    return node.label if node.label else "tau"


def save_matplotlib_fallback(net, initial_marking, final_marking, output_path):
    """Render a Petri net with matplotlib when Graphviz is unavailable."""
    graph = nx.DiGraph()
    for place in net.places:
        graph.add_node(place)
    for transition in net.transitions:
        graph.add_node(transition)
    for arc in net.arcs:
        graph.add_edge(arc.source, arc.target)

    if not graph:
        raise ValueError("Discovered Petri net has no places or transitions")

    try:
        generations = list(nx.topological_generations(graph))
        positions = {
            node: (
                generation_index * 2.5,
                (len(nodes) - 1) / 2 - node_index,
            )
            for generation_index, nodes in enumerate(generations)
            for node_index, node in enumerate(nodes)
        }
    except nx.NetworkXUnfeasible:
        positions = nx.spring_layout(graph, seed=42)

    layer_count = max(
        (int(position[0] / 2.5) + 1 for position in positions.values()),
        default=1,
    )
    layer_height = max(Counter(position[0] for position in positions.values()).values())
    figure, axis = plt.subplots(
        figsize=(max(14, layer_count * 2.5), max(7, layer_height * 1.7))
    )
    places = [node for node in graph if node in net.places]
    transitions = [node for node in graph if node in net.transitions]
    nx.draw_networkx_edges(
        graph,
        positions,
        ax=axis,
        arrows=True,
        arrowsize=16,
        edge_color="#667085",
        connectionstyle="arc3,rad=0.04",
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=places,
        node_shape="o",
        node_size=1400,
        node_color="#dbeafe",
        edgecolors="#2563eb",
        linewidths=1.5,
        ax=axis,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=transitions,
        node_shape="s",
        node_size=1500,
        node_color="#fef3c7",
        edgecolors="#d97706",
        linewidths=1.5,
        ax=axis,
    )
    labels = {}
    for node in graph:
        label = _petri_node_label(node, initial_marking, final_marking)
        if node in net.transitions and label != "tau":
            label = label.replace("_", "\n")
        labels[node] = label
    nx.draw_networkx_labels(
        graph,
        positions,
        labels=labels,
        font_size=8,
        font_weight="bold",
        ax=axis,
    )
    axis.set_title("Clinical Pathway Petri Net (matplotlib fallback)", fontsize=15)
    axis.axis("off")
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def save_visualization(net, initial_marking, final_marking, output_path):
    """Prefer pm4py's Graphviz rendering and fall back to matplotlib."""
    if shutil.which("dot"):
        try:
            import pm4py

            pm4py.save_vis_petri_net(
                net,
                initial_marking,
                final_marking,
                str(output_path),
            )
            return "Graphviz"
        except (
            ImportError,
            OSError,
            RuntimeError,
            ValueError,
            subprocess.CalledProcessError,
        ) as error:
            print(f"Graphviz rendering failed ({error}); using matplotlib fallback.")
    else:
        print("Graphviz 'dot' executable not found; using matplotlib fallback.")

    save_matplotlib_fallback(net, initial_marking, final_marking, output_path)
    return "matplotlib fallback"


def main():
    parser = argparse.ArgumentParser(
        description="Discover a clinical pathway Petri net with pm4py Inductive Miner."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_OUTPUT)
    parser.add_argument("--visual-output", type=Path, default=DEFAULT_VISUAL_OUTPUT)
    args = parser.parse_args()

    import pm4py

    events = load_event_log(str(args.input))
    event_log = format_event_log(events)
    event_log = pm4py.format_dataframe(
        event_log,
        case_id="case:concept:name",
        activity_key="concept:name",
        timestamp_key="time:timestamp",
    )
    net, initial_marking, final_marking = pm4py.discover_petri_net_inductive(
        event_log
    )

    args.model_output.parent.mkdir(parents=True, exist_ok=True)
    pm4py.write_pnml(
        net,
        initial_marking,
        final_marking,
        str(args.model_output),
    )
    renderer = save_visualization(
        net,
        initial_marking,
        final_marking,
        args.visual_output,
    )

    print(
        f"Discovered a Petri net from {event_log['case:concept:name'].nunique()} "
        f"cases and {len(event_log)} events using Inductive Miner."
    )
    print(f"Wrote PNML model to {args.model_output}.")
    print(f"Wrote Petri net visualization to {args.visual_output} ({renderer}).")


if __name__ == "__main__":
    main()
