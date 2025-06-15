#High-level functions for the most common tasks

from py3dmol.backend_3dmol import JS3DMol, EmptyViewer, get_headless_status, cleanup_headless, reinitialize_headless

def show(obj):
    """
    Create a default visualization
    :param obj: 4-letter PDB code OR filename OR MDAnalysis object OR MDTraj object OR Pybel object or OpenBabel object or CCLib data
    :return type: py3dmol.vizinterfaces.JS3DMol
    """
    raise NotImplementedError()

def view(width=400, height=400):
    """
    Create a new 3D molecular viewer instance.
    
    Args:
        width (int): Width of the viewer in pixels
        height (int): Height of the viewer in pixels
        
    Returns:
        py3dmol.backend_3dmol.EmptyViewer: A new empty viewer instance
    """
    return EmptyViewer(width=width, height=height)

#Some synonyms
visualize = viz = render = show