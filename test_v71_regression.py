from pathlib import Path
import ast

SOURCE = Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)

def test_scan_stocks_is_function():
    assert any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == 'scan_stocks' for n in TREE.body)

def test_no_scan_calls_in_ui():
    ui = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'ui')
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'scan' for n in ast.walk(ui))
    assert sum(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'scan_stocks' for n in ast.walk(ui)) == 2

def test_no_automatic_order_execution():
    run = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'run_cycle')
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ('submit_order', 'close_position', 'close_all_positions') for n in ast.walk(run))

def test_default_watchlist_contains_riot_snap():
    assert 'SOFI,F,PLUG,SNAP,RIOT' in SOURCE
