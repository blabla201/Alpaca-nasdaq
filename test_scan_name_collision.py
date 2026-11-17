import ast
from pathlib import Path

def test_scan_function_not_shadowed_in_ui():
    tree=ast.parse((Path(__file__).resolve().parents[1]/"app.py").read_text())
    ui=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="ui")
    assignments=[]
    for node in ast.walk(ui):
        if isinstance(node,(ast.Assign,ast.AnnAssign,ast.NamedExpr)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            assignments += [t for t in targets if isinstance(t,ast.Name) and t.id=="scan"]
    assert not assignments, "ui() shadows scan() function"
