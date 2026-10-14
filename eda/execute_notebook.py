"""Execute the EDA notebook with the invoking environment's interpreter."""
from pathlib import Path
import sys
import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager

root = Path(__file__).resolve().parent
notebook = root / 'part3_eda.ipynb'
nb = nbformat.read(notebook, as_version=4)
km = KernelManager(kernel_name='python3')
km.kernel_spec.argv = [sys.executable, '-m', 'ipykernel_launcher', '-f', '{connection_file}']
NotebookClient(nb, km=km, timeout=600, resources={'metadata': {'path': str(root.parent)}}).execute()
nbformat.write(nb, notebook)
print(f'Executed {notebook}')
