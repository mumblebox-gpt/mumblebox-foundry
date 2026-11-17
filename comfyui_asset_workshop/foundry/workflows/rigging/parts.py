"""Generate guided part topology in the source asset's rest coordinates."""
from math import dist, hypot

PART_TYPES = ("hand", "finger", "toes", "tail", "bird_wing", "bat_wing", "wing", "limb", "custom")
DIGITS = ("thumb", "index", "middle", "ring", "little")


def mix(a, b, t):
    return [x+(y-x)*t for x,y in zip(a,b)]


def path_points(anchors, segments):
    if type(segments) is not int or not len(anchors)-1 <= segments <= 32:
        raise ValueError("Use at least one bone per path segment, with at most 32 bones.")
    points = [anchors[0]]
    for index, (start,end) in enumerate(zip(anchors,anchors[1:])):
        count = (segments+index)//(len(anchors)-1)
        points.extend(mix(start,end,i/count) for i in range(1,count+1))
    return points


def frame(attachment, tip, width_point):
    forward = [b-a for a,b in zip(attachment,tip)]
    length = hypot(*forward)
    if length < 1e-6:
        raise ValueError("Place the tip away from the attachment.")
    unit = [value/length for value in forward]
    if width_point is None:
        axis = min(range(3),key=lambda index:abs(unit[index]))
        across = [.35*length if index==axis else 0. for index in range(3)]
    else:
        across = [b-a for a,b in zip(attachment,width_point)]
    parallel = sum(a*b for a,b in zip(across,unit))
    across = [a-parallel*b for a,b in zip(across,unit)]
    if hypot(*across) < length*.01:
        raise ValueError("Place the width guide off the centerline.")
    return across


def layout(part, attachment, tip, segments, width_point=None, waypoints=(), digit="index"):
    if part not in PART_TYPES:
        raise ValueError("Choose a supported part.")
    result = []

    def add(points, parent=None, role=None, name=None):
        for index, (head, tail) in enumerate(zip(points,points[1:])):
            if dist(head,tail)<1e-6:
                raise ValueError("Leave space between each part control point.")
            result.append({"head":head,"tail":tail,"parent":parent,"role":role or part,
                           "name":name,"segment":index+1})
            parent=len(result)-1
        return parent

    def offset(point, amount):
        return [a+b*amount for a,b in zip(point,across)]

    if part in ("hand","toes","bat_wing","bird_wing"):
        across = frame(attachment,tip,width_point)
        if part == "hand":
            palm = mix(attachment,tip,.5)
            root = add([attachment,palm],role="palm")
            for name, lateral, reach in zip(DIGITS,(-.9,-.55,-.12,.32,.68),(.69,.92,1.,.93,.79)):
                base = mix(attachment,palm,.52) if name=="thumb" else palm
                start = offset(base,lateral*.6)
                end = offset(mix(attachment,tip,reach),lateral)
                add(path_points([start,end],min(segments,4)),root,role="finger",name=name)
        elif part == "toes":
            root = add([attachment,mix(attachment,tip,.43)],role="foot")
            for index,lateral in enumerate((-.64,-.30,0.,.31,.58),1):
                start = offset(mix(attachment,tip,.42),lateral*.7)
                end = offset(mix(attachment,tip,1-.07*(index-1)),lateral)
                add(path_points([start,end],min(segments,3)),root,role="toe",name=f"toe_{index}")
        else:
            elbow = waypoints[0] if waypoints else offset(mix(attachment,tip,.38),-.24)
            wrist = waypoints[-1] if len(waypoints)>1 else mix(attachment,tip,.68)
            root = add([attachment,elbow,wrist,tip],role="wing")
            anchor = result[root]["parent"]
            for index,reach in enumerate((.96,.83,.7,.55),1):
                end = offset(mix(attachment,tip,reach),.6+index*.18)
                if part=="bat_wing":
                    points = path_points([wrist,mix(wrist,end,.5),end],max(2,min(segments,4)))
                    role = "wing_digit"
                else:
                    base = mix(elbow,wrist,index/5)
                    points = [base,end]
                    role = "feather"
                add(points,anchor,role=role,name=f"{role}_{index}")
    else:
        if part=="finger" and digit not in DIGITS:
            raise ValueError("Choose a finger identity.")
        role = {"custom":"other","limb":"other"}.get(part,part)
        add(path_points([attachment,*waypoints,tip],segments),role=role,name=digit if part=="finger" else None)
    return result


def part_group(part):
    return "wing" if part in ("bird_wing","bat_wing") else part
