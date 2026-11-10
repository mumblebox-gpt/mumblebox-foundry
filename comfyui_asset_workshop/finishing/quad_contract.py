"""Polygon-preserving contracts shared by isolated finishing workers."""
import math,re
from pathlib import Path

def safe_name(name):
    if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',name) or '..' in name:
        raise ValueError('Use a simple export name without directories')
    return name

def validate_polygons(vertices,faces):
    if not len(vertices) or not len(faces): raise ValueError('Empty geometry')
    if any(len(v)!=3 or not all(math.isfinite(float(x)) for x in v) for v in vertices): raise ValueError('Nonfinite XYZ coordinates')
    for f in faces:
        if len(f)<3 or len(set(f))!=len(f) or any(int(i)!=i or i<0 or i>=len(vertices) for i in f): raise ValueError('Invalid polygon indices')

def write_obj(path,vertices,faces):
    validate_polygons(vertices,faces)
    with Path(path).open('w',encoding='utf-8') as out:
        for v in vertices: out.write('v '+' '.join(format(float(x),'.9g') for x in v)+'\n')
        for f in faces: out.write('f '+' '.join(str(int(i)+1) for i in f)+'\n')

def read_obj(path):
    vertices=[]; faces=[]
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        fields=line.split()
        if not fields:continue
        if fields[0]=='v': vertices.append([float(x) for x in fields[1:4]])
        elif fields[0]=='f':
            f=[int(x.split('/')[0]) for x in fields[1:]]
            faces.append([i-1 if i>0 else len(vertices)+i for i in f])
    validate_polygons(vertices,faces)
    return vertices,faces

def normalize_quad_diagonals(faces):
    """Keep fixed fan diagonals distinct from polygon edges and one another."""
    def edge(a, b):
        return (a, b) if a < b else (b, a)

    result = [list(face) for face in faces]
    occupied = {edge(face[i], face[(i + 1) % len(face)])
                for face in result for i in range(len(face))}
    choices = {}
    for index, face in enumerate(result):
        if len(face) == 4:
            options = (edge(face[0], face[2]), edge(face[1], face[3]))
            choices[index] = [(i, key) for i, key in enumerate(options) if key not in occupied]

    rotations = 0
    # Give quads with only one safe choice first access to that diagonal.
    for index in sorted(choices, key=lambda i: len(choices[i])):
        selected = next(((rotation, key) for rotation, key in choices[index] if key not in occupied), None)
        if selected is None:
            raise ValueError("Quad has no safe fixed diagonal")
        rotation, key = selected
        occupied.add(key)
        if rotation:
            face = result[index]
            result[index] = face[1:] + face[:1]
            rotations += 1
    return result, rotations


def allocate_budget(areas,total,minimum=24):
    if not areas or total<len(areas)*minimum or any(not math.isfinite(float(a)) or a<0 for a in areas) or sum(areas)<=0:raise ValueError('Invalid component budget')
    remaining=total-len(areas)*minimum
    raw=[remaining*a/sum(areas) for a in areas]
    result=[minimum+math.floor(x) for x in raw]
    order=sorted(range(len(areas)),key=lambda i:raw[i]-math.floor(raw[i]),reverse=True)
    for i in order[:total-sum(result)]:result[i]+=1
    return result

def subdivide_to_quads(vertices, faces):
    """Subdivide polygons conformingly with shared edge midpoints."""
    v = [list(map(float, x)) for x in vertices]
    edges = {}
    quads = []
    for polygon in faces:
        face = [int(index) for index in polygon]
        mids = []
        for left, right in zip(face, face[1:] + face[:1]):
            key = tuple(sorted((left, right)))
            if key not in edges:
                edges[key] = len(v)
                v.append([(v[left][j] + v[right][j]) / 2 for j in range(3)])
            mids.append(edges[key])
        center = len(v)
        v.append([sum(v[index][j] for index in face) / len(face) for j in range(3)])
        for i, corner in enumerate(face):
            quads.append([corner, mids[i], center, mids[i - 1]])
    return v, quads
