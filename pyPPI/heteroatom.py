import numpy as np
import os

from scipy.linalg import norm
from scipy.spatial import cKDTree

from Bio.PDB.PDBParser import PDBParser
import Bio.PDB.ResidueDepth as ResidueDepth
from Bio.PDB.ResidueDepth import get_surface

from .ASA import KNOWN_RADIUS, R_WATER
from .DBConfig import get_connection

RESULTS_DIR = './results/'

def print_rand_points(pdb, points):
    """Prints rand point to file
        :param points: points to print
        """
    cavity_file =  pdb.name + '_cavities_in.pdb'
    with open(cavity_file, 'w') as rand_point_file:
        q_points = 0
        res = 1
        atoms_per_res = find_atoms_per_res(len(points))
        for x, y, z in points:
            q_points += 1
            point_to_print = 'HETATM{0:^5}  O   HOH I{1:^4}    {2:^7.3f} {3:^7.3f} {4:^7.3f}  1.00 43.38          O'.format(q_points, res, x, y, z)
            print(point_to_print, file=rand_point_file)
            if atoms_per_res == 0:
                res += 1
            else:
                if q_points % (10 * atoms_per_res) == 0:
                    res +=1

    
def find_atoms_per_res(number_of_atoms):
    if number_of_atoms < 10000 and number_of_atoms > 9999:
        return 1
    elif len(str(int(number_of_atoms))) <= 4:
        return 0
    else:
        return 1 + find_atoms_per_res(number_of_atoms / 10)

def calculateVolume(pdb, interface):
    
    rand_points, pointsToCheck, allVolume = createRandPoints(interface)
    print('Number of total points:', pointsToCheck)
    rand_points = inInterface(rand_points, pdb, interface)
    print('Points in Interface:', len(rand_points))
    rand_points = notinVDWspheres(rand_points, pdb)
    print('Points out of van der Waals spheres:', len(rand_points))
    
    print_rand_points(pdb, rand_points)
    is_ligand_interface(pdb)
    
def createRandPoints(interface):
    
    ACCURACY = 1.0 ** 3
    ACCURACY_FACTOR = 1.0

    # find bounding box
    boundingBox = []
    for i in range(0, 3):
        axisCoords = [a.coord[i] for a in interface]
        try:
            boundingBox.append((min(axisCoords), max(axisCoords)))
        except:
            continue
    
    distances = [maxAxis - minAxis for minAxis, maxAxis in boundingBox]
    allVolume = np.prod(distances)
    pointsToCheck = int((ACCURACY_FACTOR * (allVolume / ACCURACY)) * 2)
    
    rand_points = np.random.rand(pointsToCheck, 3)
    for i, min_max in enumerate(boundingBox):
        rand_points[:, i] *= min_max[1] - min_max[0]
        rand_points[:, i] += min_max[0]
    
    return rand_points, pointsToCheck, allVolume

def inInterface(rand_points, pdb, interface):
    
    components = [[a for a in interface if a.chain in part] for part in pdb.interfaceParts]
    partResIds = [set((a.chain, a.resId, a.iCode) for a in part) for part in components]
    interfaceRes = [[a for a in pdb.atoms if (a.chain, a.resId, a.iCode) in partResIds] for part, partResIds
                    in zip(pdb.interfaceParts, partResIds)]
    
    aTree = cKDTree(np.array([a.coord for a in interfaceRes[0]]))
    bTree = cKDTree(np.array([a.coord for a in interfaceRes[1]]))
    
    aDistances, neighbors_a = aTree.query(rand_points)
    bDistances, neighbors_b = bTree.query(rand_points)
    
    nearA = np.array([a for a in interfaceRes[0]])[neighbors_a]
    nearB = np.array([a for a in interfaceRes[1]])[neighbors_b]

    ab_Distance = norm(np.array([a.coord for a in nearA]) - np.array([a.coord for a in nearB]), axis=1)
    
    selector = (aDistances < ab_Distance) & (bDistances < ab_Distance)
   
    return rand_points[selector]

def onlyBuried(rand_points, pdb):
    
    parser = PDBParser(PERMISSIVE=1)
    structure = parser.get_structure(pdb.name, pdb.file)
    model = structure[0]
    
    surface = get_surface(model, probe_radius=2.5)
    debug_surface(surface, pdb)
    
    pdbTree = pdb.ktree
    _, atomDistances = pdbTree.findNearest(query_point=rand_points, num=1)
    
    surfaceTree = cKDTree(surface)
    surfaceDistances, _ = surfaceTree.query(rand_points)
    
    selector = (atomDistances < surfaceDistances) & (surfaceDistances > 1.0)
    
    rand_points = rand_points[selector]
    return rand_points

def notinVDWspheres(rand_points, pdb):
    for element in KNOWN_RADIUS.keys():
        element_coords = [a.coord for a in pdb.atoms if a.atomType == element]
        if not any(element_coords):
            continue
        elementTree = cKDTree(element_coords)
        points_in_VDW_radius = elementTree.query_ball_point(rand_points, 0)
        selector = (points_in_VDW_radius.astype(bool) == False)
        rand_points = rand_points[selector]
        if not np.any(rand_points):
            print('No cavities in ' + pdb.name)
            break
    
    return rand_points


def is_ligand_interface(pdb):

    parser = PDBParser(PERMISSIVE=1)
    structure = parser.get_structure(pdb.name, pdb.file)
    model = structure[0]

    interface_atom_coo = []
    try:
        structure2 = parser.get_structure(pdb.file,'%s_cavities_in.pdb' % pdb.name)
        for model2 in structure2:
            for chain2 in model2:
                for residue2 in chain2:
                    for atom2 in residue2:
                        interface_atom_coo.append(atom2)



        list_of_ligand_distance = []
        for atoms in structure.get_atoms():
            tags = atoms.get_full_id()
            if tags[3][0] != " ":
                if tags[3][0] != 'W':
                    list_of_ligand_distance.append(atoms)

        distances_ll = []
        for aa in interface_atom_coo:
            for bb in list_of_ligand_distance:
                distances_ll.append(abs(aa-bb))
                
        # with open('ligand in the interface.csv', mode='w') as ll:
        #     if any(yy < 2 for yy in distances_ll):
        #       print('There are ligannds in the %s interface' % pdb.name, file= ll)
        #     else:
        #       print('There are no ligands in the %s interface' % pdb.name, file= ll)

        return distances_ll
    except:
            pass