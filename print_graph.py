from IPython.display import Image, display

from langgraph.graph import StateGraph, START, END

builder = StateGraph(State)

builder.add_node("node_1", node_1)

builder.add_node("node_2", node_2)

builder.add_node("node_3", node_3)

builder.add_edge(START, "node_1")

builder.add_conditional_edges("node_1", decide_mood)

builder.add_edge("node_2", END)

builder.add_edge("node_3", END)

graph = builder.compile()

display(Image(graph.get_graph().draw_mermaid_png()))