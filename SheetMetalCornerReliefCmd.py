# -*- coding: utf-8 -*-
###################################################################################
#
#  SheetMetalCornerReliefCmd.py
#
#  Copyright 2020 Jaise James <jaisekjames at gmail dot com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#
###################################################################################

from FreeCAD import Gui
from PySide import QtCore, QtGui

import FreeCAD, Part, os, math
__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Resources', 'icons' )
smEpsilon = 0.0000001

import BOPTools.SplitFeatures, BOPTools.JoinFeatures
import SheetMetalBendSolid
import SheetMetalBaseCmd

def smWarnDialog(msg):
    diag = QtGui.QMessageBox(QtGui.QMessageBox.Warning, 'Error in macro MessageBox', msg)
    diag.setWindowModality(QtCore.Qt.ApplicationModal)
    diag.exec_()

def smBelongToBody(item, body):
    if (body is None):
        return False
    for obj in body.Group:
        if obj.Name == item.Name:
            return True
    return False

def smIsPartDesign(obj):
    return str(obj).find("<PartDesign::") == 0

def smIsOperationLegal(body, selobj):
    #FreeCAD.Console.PrintLog(str(selobj) + " " + str(body) + " " + str(smBelongToBody(selobj, body)) + "\n")
    if smIsPartDesign(selobj) and not smBelongToBody(selobj, body):
        smWarnDialog("The selected geometry does not belong to the active Body.\nPlease make the container of this item active by\ndouble clicking on it.")
        return False
    return True

def smthk(obj, foldface) :
  normal = foldface.normalAt(0,0)
  theVol = obj.Volume
  if theVol < 0.0001:
      SMError("Shape is not a real 3D-object or to small for a metal-sheet!")
  else:
      # Make a first estimate of the thickness
      estimated_thk = theVol/(obj.Area / 2.0)
#  p1 = foldface.CenterOfMass
  for v in foldface.Vertexes :
    p1 = v.Point
    p2 = p1 + estimated_thk * -1.5 * normal
    e1 = Part.makeLine(p1, p2)
    thkedge = obj.common(e1)
    thk = thkedge.Length
    if thk > smEpsilon :
      break
  return thk

def smCutFace(Face, obj) :
  # find face Modified During loop
  for face in obj.Faces :
    face_common = face.common(Face)
    if face_common.Faces :
      break
  return face

def smGetEdge(Face, obj) :
  # find Edges that overlap
  for edge in obj.Edges :
    face_common = edge.common(Face)
    if face_common.Edges :
      break
  return edge

def smGetEdgelist(Face, obj) :
  # find Edges that overlap
  edgelist=[]
  for edge in obj.Edges :
    face_common = edge.common(Face)
    if face_common.Edges :
      edgelist.append(edge)
  return edgelist

def makeSketch(relieftype, size, ratio, cent, normal, addvector):
  # create wire for face creation
  if "Circle" in relieftype :
    circle = Part.makeCircle(size, cent, normal)
    sketch = Part.Wire(circle)
  else :
#    diagonal_length = math.sqrt(size**2 + (ratio * size)**2)
    diagonal_length = size * 2
    opposite_vector = normal.cross(addvector).normalize()
    pt1 = cent + addvector * diagonal_length / 2.0
    pt2 = cent + opposite_vector * diagonal_length / 2.0
    pt3 = cent + addvector * -diagonal_length / 2.0
    pt4 = cent + opposite_vector * -diagonal_length / 2.0
    rect = Part.makePolygon([pt1,pt2,pt3,pt4,pt1])
    sketch = Part.Wire(rect)
  #Part.show(sketch,'sketch')
  return sketch

def equal_angle(ang1, ang2, p=5):
  # compares two angles
  result = False
  if round(ang1 - ang2, p)==0:
    result = True
  if round((ang1-2.0*math.pi) - ang2, p)==0:
    result = True
  if round(ang1 - (ang2-2.0*math.pi), p)==0:
    result = True
  return result

def bendAngle(theFace, edge_vec) :
  #Start to investigate the angles at self.__Shape.Faces[face_idx].ParameterRange[0]
  #Part.show(theFace,"theFace")
  #valuelist =  theFace.ParameterRange
  #print(valuelist)
  angle_0 = theFace.ParameterRange[0]
  angle_1 = theFace.ParameterRange[1]

  # idea: identify the angle at edge_vec = P_edge.Vertexes[0].copy().Point
  # This will be = angle_start
  # calculate the tan_vec from valueAt
  edgeAngle, edgePar = theFace.Surface.parameter(edge_vec)
  #print('the angles: ', angle_0, ' ', angle_1, ' ', edgeAngle, ' ', edgeAngle - 2*math.pi)

  if equal_angle(angle_0, edgeAngle):
    angle_start = angle_0
    angle_end = angle_1
  else:
    angle_start = angle_1
    angle_end = angle_0

  bend_angle = angle_end - angle_start
#  angle_tan = angle_start + bend_angle/6.0 # need to have the angle_tan before correcting the sign

  if bend_angle < 0.0:
    bend_angle = -bend_angle

  #print(math.degrees(bend_angle))
  return math.degrees(bend_angle)

def getCornerPoint(edge1,edge2):
  pt1 = edge1.valueAt(edge1.FirstParameter)
  pt2 = edge1.valueAt(edge1.LastParameter)
  pt3 = edge2.valueAt(edge2.FirstParameter)
  pt4 = edge2.valueAt(edge2.LastParameter)

  e1 = Part.Line(pt1, pt2).toShape()
  #Part.show(e1,'e1')
  e2 = Part.Line(pt3, pt4).toShape()
  #Part.show(e2,'e2')
  section = e1.section(e2)
  #Part.show(section1,'section1')
  cornerPoint = section.Vertexes[0].Point
  return cornerPoint

def LineExtend(edge, distance):
  pt1 = edge.valueAt(edge.FirstParameter)
  pt2 = edge.valueAt(edge.LastParameter)
  EdgeVector = pt1 - pt2
  EdgeVector.normalize()
  #print([pt1, pt2, EdgeVector] )
  ExtLine = Part.makeLine(pt1+ EdgeVector * distance, pt2+ EdgeVector * -distance)
  #Part.show(ExtLine,"ExtLine")
  return ExtLine

def getBendDetail(obj, edge1, edge2, kfactor) :
  #To get adjacent face list from edges
  facelist1 = obj.ancestorsOfType(edge1, Part.Face)
#  facelist2 = obj.ancestorsOfType(edge2, Part.Face)
  cornerPoint = getCornerPoint(edge1,edge2)

  #To get top face edges
  ExtLinelist = [LineExtend(edge1, edge1.Length), LineExtend(edge2, edge2.Length)]
  Edgewire = BOPTools.JoinFeatures.JoinAPI.connect(ExtLinelist, tolerance = 0.0001)
  #Part.show(Edgewire,"Edgewire")

  #To get top face
  for Planeface in facelist1 :
    if issubclass(type(Planeface.Surface),Part.Plane) :
      largeface = Planeface
      break
  #Part.show(largeface,"largeface")

  #To get bend radius
  for cylface in facelist1 :
    if issubclass(type(cylface.Surface),Part.Cylinder) :
#      bendR = cylface.Surface.Radius
      break

  #To get thk of sheet, top face normal, bend angle
#  normal = largeface.normalAt(0,0)
  thk = smthk(obj, largeface)
  bendA = bendAngle(cylface, cornerPoint)
  #print([thk, bendA])

  #To check bend direction
  offsetface = cylface.makeOffsetShape(-thk, 0.0, fill = False)
  #Part.show(offsetface,"offsetface")
  if offsetface.Area < cylface.Area :
    bendR = cylface.Surface.Radius - thk
#    size = size + thk
  else :
    bendR = cylface.Surface.Radius

  #To arrive unfold Length, neutralRadius
  unfoldLength = ( bendR + kfactor * thk ) * bendA * math.pi / 180.0
  neutralRadius =  ( bendR + kfactor * thk )

  #To get centre of sketch
  neutralEdges = Edgewire.makeOffset2D(unfoldLength/2.0,fill = False, openResult = True, join = 2, intersection = False)
  neutralFaces = Edgewire.makeOffset2D(unfoldLength, fill = True, openResult = True, join = 2, intersection = False)
  First_Check_face = largeface.common(neutralFaces)
  if First_Check_face.Faces :
    neutralEdges = Edgewire.makeOffset2D(-unfoldLength/2.0, fill = False, openResult = True, join = 2, intersection = False)
  #Part.show(neutralEdges,"neutralEdges")

  # To work around offset2d issue [2 line offset produce 3 lines]
  for offsetvertex in neutralEdges.Vertexes :
    Edgelist = neutralEdges.ancestorsOfType(offsetvertex, Part.Edge)
    #print(len(Edgelist))
    if len(Edgelist) > 1 :
      e1 = Edgelist[0].valueAt(Edgelist[0].LastParameter) - Edgelist[0].valueAt(Edgelist[0].FirstParameter)
      e2 = Edgelist[1].valueAt(Edgelist[1].LastParameter) - Edgelist[1].valueAt(Edgelist[1].FirstParameter)
      angle_rad = e1.getAngle(e2)
      if angle_rad > smEpsilon :
        break
  centerPoint = offsetvertex.Point
  #print(centerPoint)
  return [cornerPoint, centerPoint, largeface, thk, unfoldLength, neutralRadius]

def smCornerR(reliefsketch = "Circle", size = 3.0, ratio = 1.0, xoffset = 0.0, yoffset = 0.0, kfactor = 0.5, sketch = '',
                            flipped = False, selEdgeNames = '', MainObject = None):

  resultSolid = MainObject.Shape.copy()
  REdgelist = []
  for selEdgeName in selEdgeNames:
    REdge = resultSolid.getElement(selEdgeName)
    REdgelist.append(REdge)

  DetailList = getBendDetail(resultSolid, REdgelist[0], REdgelist[1], kfactor)
  cornerPoint, centerPoint, LargeFace, thk, unfoldLength, neutralRadius = DetailList
  normal = LargeFace.normalAt(0,0)

  SplitLineVector = centerPoint - cornerPoint
  if "Scaled" in reliefsketch :
    size = ratio * abs(SplitLineVector.Length)
  SplitLineVector.normalize()
  #print([centerPoint, cornerPoint, SplitLineVector] )
  SplitLine = Part.makeLine(centerPoint+ SplitLineVector * size * 3, cornerPoint+ SplitLineVector * -size * 3)
  #Part.show(SplitLine,"SplitLine")

  if reliefsketch != "Sketch" :
    sketch = makeSketch(reliefsketch, size, ratio, centerPoint, normal, SplitLineVector)
    reliefFace = Part.Face(sketch)
  else :
    reliefFace = Part.Face(sketch.Shape.Wires[0])
  #Part.show(reliefFace,'reliefFace')

  #To check face direction
  coeff = normal.dot(reliefFace.Faces[0].normalAt(0,0))
  if coeff < 0 :
    reliefFace.reverse()

  # to get top face cut
  First_face = LargeFace.common(reliefFace)
  #Part.show(First_face,'First_face')
  Balance_Face = reliefFace.cut(First_face)
  #Part.show(Balance_Face,'Balance_Face')

  #To get bend solid face
  SplitFaces = BOPTools.SplitAPI.slice(Balance_Face.Faces[0], SplitLine.Edges, "Standard", 0.0)
  #Part.show(SplitFaces,"SplitFaces")

  #To get top face normal, flatsolid
  solidlist = []
  if First_face.Faces:
    Flatsolid = First_face.extrude(normal * -thk)
    #Part.show(Flatsolid,"Flatsolid")
    solidlist.append(Flatsolid)

  if SplitFaces.Faces :
    for BalanceFace in SplitFaces.Faces :
      #Part.show(BalanceFace,"BalanceFace")
      TopFace = LargeFace
      #Part.show(TopFace,"TopFace")
      while BalanceFace.Faces :
        BendEdgelist = smGetEdgelist(BalanceFace, TopFace)
        for BendEdge in BendEdgelist :
          #Part.show(BendEdge,"BendEdge")
          edge_facelist = resultSolid.ancestorsOfType(BendEdge, Part.Face)
          for cyl_face in edge_facelist :
            #print(type(cyl_face.Surface))
            if issubclass(type(cyl_face.Surface),Part.Cylinder) :
              break
          if issubclass(type(cyl_face.Surface),Part.Cylinder) :
            break
        #Part.show(BendEdge,"BendEdge")
        facelist = resultSolid.ancestorsOfType(BendEdge, Part.Face)

        #To get bend radius, bend angle
        for cylface in facelist :
          if issubclass(type(cylface.Surface),Part.Cylinder) :
            break
        if not(issubclass(type(cylface.Surface),Part.Cylinder)) :
          break
        #Part.show(cylface,"cylface")
        for planeface in facelist :
          if issubclass(type(planeface.Surface),Part.Plane) :
            break
        #Part.show(planeface,"planeface")
        normal = planeface.normalAt(0,0)
        revAxisV = cylface.Surface.Axis
        revAxisP = cylface.Surface.Center
        bendA = bendAngle(cylface, revAxisP)
        #print([bendA, revAxisV, revAxisP, cylface.Orientation])

        #To check bend direction
        offsetface = cylface.makeOffsetShape(-thk, 0.0, fill = False)
        #Part.show(offsetface,"offsetface")
        if offsetface.Area < cylface.Area :
          bendR = cylface.Surface.Radius - thk
          flipped = True
        else :
          bendR = cylface.Surface.Radius
          flipped = False

        #To arrive unfold Length, neutralRadius
        unfoldLength = ( bendR + kfactor * thk ) * abs(bendA) * math.pi / 180.0
        neutralRadius =  ( bendR + kfactor * thk )
        #print([unfoldLength,neutralRadius])

        #To get faceNormal, bend face
        faceNormal = normal.cross(revAxisV).normalize()
        #print(faceNormal)
        if bendR < cylface.Surface.Radius :
          offsetSolid = cylface.makeOffsetShape(bendR/2.0, 0.0, fill = True)
        else:
          offsetSolid = cylface.makeOffsetShape(-bendR/2.0, 0.0, fill = True)
        #Part.show(offsetSolid,"offsetSolid")
        tool = BendEdge.copy()
        FaceArea = tool.extrude(faceNormal * -unfoldLength )
        #Part.show(FaceArea,"FaceArea")
        #Part.show(BalanceFace,"BalanceFace")
        SolidFace = offsetSolid.common(FaceArea)
        if not(SolidFace.Faces):
          faceNormal = faceNormal * -1
          FaceArea = tool.extrude(faceNormal * -unfoldLength )
        BendSolidFace = BalanceFace.common(FaceArea)
        #Part.show(FaceArea,"FaceArea")
        #Part.show(BendSolidFace,"BendSolidFace")
        #print([bendR, bendA, revAxisV, revAxisP, normal, flipped, BendSolidFace.Faces[0].normalAt(0,0)])

        bendsolid = SheetMetalBendSolid.BendSolid(BendSolidFace.Faces[0], BendEdge, bendR, thk, neutralRadius, revAxisV, flipped)
        #Part.show(bendsolid,"bendsolid")
        solidlist.append(bendsolid)

        if flipped == True:
          bendA = -bendA
        if not(SolidFace.Faces):
          revAxisV = revAxisV * -1
        sketch_face = BalanceFace.cut(BendSolidFace)
        sketch_face.translate(faceNormal * unfoldLength)
        #Part.show(sketch_face,"sketch_face")
        sketch_face.rotate(revAxisP, -revAxisV, bendA)
        #Part.show(sketch_face,"Rsketch_face")
        CylEdge = smGetEdge(sketch_face, cylface)
        #Part.show(CylEdge,"CylEdge")
        edgefacelist = resultSolid.ancestorsOfType(CylEdge, Part.Face)
        for TopFace in edgefacelist :
          if not(issubclass(type(TopFace.Surface),Part.Cylinder)) :
            break
        #Part.show(TopFace,"TopFace")

        #To get top face normal, flatsolid
        normal = TopFace.normalAt(0,0)
        Flatface = sketch_face.common(TopFace)
        BalanceFace = sketch_face.cut(Flatface)
        #Part.show(BalanceFace,"BalanceFace")
        if Flatface.Faces :
          BalanceFace = sketch_face.cut(Flatface)
          #Part.show(BalanceFace,"BalanceFace")
          Flatsolid = Flatface.extrude(normal * -thk)
          #Part.show(Flatsolid,"Flatsolid")
          solidlist.append(Flatsolid)
        else:
          BalanceFace = sketch_face

  #To get relief Solid fused
  if len(solidlist) > 1 :
    SMSolid = solidlist[0].multiFuse(solidlist[1:])
    #Part.show(SMSolid,"SMSolid")
    SMSolid = SMSolid.removeSplitter()
  else :
   SMSolid = solidlist[0]
  #Part.show(SMSolid,"SMSolid")
  resultSolid = resultSolid.cut(SMSolid)
  return resultSolid

class SMCornerRelief:
  def __init__(self, obj):
    '''"Add Corner Relief to Sheetmetal Bends" '''
    selobj = Gui.Selection.getSelectionEx()

    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Corner Relief Type")
    obj.addProperty("App::PropertyEnumeration", "ReliefSketch", "Parameters",_tip_).ReliefSketch = ["Circle", "Circle-Scaled", "Square", "Square-Scaled", "Sketch"]
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Base object")
    obj.addProperty("App::PropertyLinkSub", "baseObject", "Parameters",_tip_).baseObject = (selobj[0].Object, selobj[0].SubElementNames)
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Size of Shape")
    obj.addProperty("App::PropertyLength","Size","Parameters",_tip_).Size = 3.0
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Size Ratio of Shape")
    obj.addProperty("App::PropertyFloat","SizeRatio","Parameters",_tip_).SizeRatio = 1.5
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Neutral Axis Position")
    obj.addProperty("App::PropertyFloatConstraint","kfactor","Parameters",_tip_).kfactor = (0.5,0.0,1.0,0.01)
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Corner Relief Sketch")
    obj.addProperty("App::PropertyLink","Sketch","Parameters1",_tip_)
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Gap from side one")
    obj.addProperty("App::PropertyDistance","XOffset","Parameters1",_tip_).XOffset = 0.0
    _tip_ = QtCore.QT_TRANSLATE_NOOP("App::Property","Gap from side two")
    obj.addProperty("App::PropertyDistance","YOffset","Parameters1",_tip_).YOffset = 0.0
    obj.Proxy = self

  def execute(self, fp):
    '''"Print a short message when doing a recomputation, this method is mandatory" '''

    s = smCornerR(reliefsketch = fp.ReliefSketch, ratio = fp.SizeRatio, size = fp.Size.Value, kfactor = fp.kfactor,
                    xoffset = fp.XOffset.Value, yoffset = fp.YOffset.Value, sketch = fp.Sketch, selEdgeNames = fp.baseObject[1],
                    MainObject = fp.baseObject[0])
    fp.Shape = s

    Gui.ActiveDocument.getObject(fp.baseObject[0].Name).Visibility = False
    if fp.Sketch :
      Gui.ActiveDocument.getObject(fp.Sketch.Name).Visibility = False

class SMCornerReliefVP:
  "A View provider that nests children objects under the created one"

  def __init__(self, obj):
    obj.Proxy = self
    self.Object = obj.Object

  def attach(self, obj):
    self.Object = obj.Object
    return

  def updateData(self, fp, prop):
    return

  def getDisplayModes(self,obj):
    modes=[]
    return modes

  def setDisplayMode(self,mode):
    return mode

  def onChanged(self, vp, prop):
    return

  def __getstate__(self):
    #        return {'ObjectName' : self.Object.Name}
    return None

  def __setstate__(self,state):
    if state is not None:
      import FreeCAD
      doc = FreeCAD.ActiveDocument #crap
      self.Object = doc.getObject(state['ObjectName'])

  def claimChildren(self):
    objs = []
    if hasattr(self.Object,"baseObject"):
      objs.append(self.Object.baseObject[0])
      objs.append(self.Object.Sketch)
    return objs

  def getIcon(self):
    return os.path.join( iconPath , 'SheetMetal_AddCornerRelief.svg')

class SMCornerReliefPDVP:
  "A View provider that nests children objects under the created one"

  def __init__(self, obj):
    obj.Proxy = self
    self.Object = obj.Object

  def attach(self, obj):
    self.Object = obj.Object
    return

  def updateData(self, fp, prop):
    return

  def getDisplayModes(self,obj):
    modes=[]
    return modes

  def setDisplayMode(self,mode):
    return mode

  def onChanged(self, vp, prop):
    return

  def __getstate__(self):
    #        return {'ObjectName' : self.Object.Name}
    return None

  def __setstate__(self,state):
    if state is not None:
      import FreeCAD
      doc = FreeCAD.ActiveDocument #crap
      self.Object = doc.getObject(state['ObjectName'])

  def claimChildren(self):
    objs = []
    if hasattr(self.Object,"Sketch"):
      objs.append(self.Object.Sketch)
    return objs

  def getIcon(self):
    return os.path.join( iconPath , 'SheetMetal_AddCornerRelief.svg')

class AddCornerReliefCommandClass():
  """Add Corner Relief command"""

  def GetResources(self):
    return {'Pixmap'  : os.path.join( iconPath , 'SheetMetal_AddCornerRelief.svg'), # the name of a svg file available in the resources
            'MenuText': QtCore.QT_TRANSLATE_NOOP('SheetMetal','Add Corner Relief'),
            'Accel': "C, R",
            'ToolTip' : QtCore.QT_TRANSLATE_NOOP('SheetMetal','Corner Relief to metal sheet corner.\n'
            '1. Select 2 Edges (on flat face that shared with bend faces) to create Relief on sheetmetal.\n'
            '2. Use Property editor to modify default parameters')}

  def Activated(self):
    doc = FreeCAD.ActiveDocument
    view = Gui.ActiveDocument.ActiveView
    activeBody = None
    selobj = Gui.Selection.getSelectionEx()[0].Object
    viewConf = SheetMetalBaseCmd.GetViewConfig(selobj)
    if hasattr(view,'getActiveObject'):
      activeBody = view.getActiveObject('pdbody')
    if not smIsOperationLegal(activeBody, selobj):
        return
    doc.openTransaction("Corner Relief")
    if activeBody is None or not smIsPartDesign(selobj):
      a = doc.addObject("Part::FeaturePython","CornerRelief")
      SMCornerRelief(a)
      SMCornerReliefVP(a.ViewObject)
    else:
      #FreeCAD.Console.PrintLog("found active body: " + activeBody.Name)
      a = doc.addObject("PartDesign::FeaturePython","CornerRelief")
      SMCornerRelief(a)
      SMCornerReliefPDVP(a.ViewObject)
      activeBody.addObject(a)
    SheetMetalBaseCmd.SetViewConfig(a, viewConf)
    doc.recompute()
    doc.commitTransaction()
    return

  def IsActive(self):
    if len(Gui.Selection.getSelection()) < 1 or len(Gui.Selection.getSelectionEx()[0].SubElementNames) < 2:
      return False
#    selobj = Gui.Selection.getSelection()[0]
    for selVertex in Gui.Selection.getSelectionEx()[0].SubObjects:
      if type(selVertex) != Part.Edge :
        return False
    return True

Gui.addCommand('SMCornerRelief',AddCornerReliefCommandClass())

