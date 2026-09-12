# Build with: .venv\Scripts\python.exe -m PyInstaller --noconfirm Hexassist.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, get_package_paths

root = Path(SPECPATH)
datas = [
    (str(root / "data" / "catalog.json"), "data"),
    (str(root / "examples" / "selection_demo.png"), "examples"),
    (str(root / "build_assets" / "seed"), "seed"),
    (str(root / "build_assets" / "manifest.json"), "build_info"),
    (str(root / "README.md"), "help"),
]
datas += collect_data_files("customtkinter")
datas += collect_data_files("rapidocr_onnxruntime")
binaries = collect_dynamic_libs("onnxruntime")
# RapidOCR adds its own package directory to sys.path and imports these three
# packages by their short names from config.yaml. Match that layout in the archive.
_, rapidocr_path = get_package_paths("rapidocr_onnxruntime")
a = Analysis(
    [str(root / "app.py")], pathex=[str(root), rapidocr_path], binaries=binaries, datas=datas,
    hiddenimports=["onnxruntime.capi.onnxruntime_pybind11_state",
                   "ch_ppocr_v3_det", "ch_ppocr_v3_rec", "ch_ppocr_v2_cls"],
    hookspath=[], runtime_hooks=[], excludes=["matplotlib", "IPython", "notebook", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="海克斯助手", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False, disable_windowed_traceback=False,
    icon=str(root / "build_assets" / "hexassist.ico"),
)
