from __future__ import annotations

from tkinter import *
from tkinter import ttk
import tkinter.font as tkFont
import tkinter.filedialog
import tkinter.messagebox
from tkinter import scrolledtext 
from time import *
from collections import defaultdict
import bisect
from typing import *
import pyclip
import math
import copy

from enum import Enum,IntEnum

class KeyDependentDefaultDict(defaultdict):
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(key)
            return ret

class Dir(IntEnum):
	NW = 0
	NE = 1
	E = 2
	SE = 3
	SW = 4
	W = 5

class Hex:
	# is this class useful?

	s_mpDirDxDy = [(0,1), (1,1), (1,0), (0,-1), (-1,-1), (-1,0)]
	s_setHex:Set[Hex] = set()

	@staticmethod
	def Init():
		rowdefs = [(0,5), (0,6), (0,7), (0,8), (0,9), (0,10), (0,11), (0,11), (1,10), (2,9)]
		for y,(xMic,c) in enumerate(rowdefs):
			for x in range(xMic, xMic + c):
				Hex.s_setHex.add(Hex(x,y))

	def __init__(self, x, y):
		self.x = x  # E from lower left
		self.y = y  # NW from lower left

	def __repr__(self):
		return f"Hex{(self.x,self.y)}"

	def __eq__(self, other):
		if isinstance(other, Hex):
			return self.x == other.x and self.y == other.y
		return NotImplemented
	
	def __hash__(self):
		return hash((self.x, self.y))

	@staticmethod
	def All():
		return Hex.s_setHex

	def Neighbor(self, dir):
		dX,dY = Hex.s_mpDirDxDy[dir]
		hex = Hex(self.x + dX, self.y + dY)
		return hex if hex in Hex.s_setHex else None

	def Neighbors(self):
		# BB cache this?

		hexes = []
		for dir in Dir:
			hex = self.Neighbor(dir)
			if hex !=  None:
				hexes.append(hex)
		return hexes

class Side(IntEnum):
	Red = 0
	White = 1 # "Ivory" in official rules

class Viking:
	def __init__(self, side, i):
		self.side = side
		self.i = i # needed at all?

class Move:
	def __init__(self, vik, hexFrom, hexTo, hexStone):
		self.vik = vik
		self.hexFrom = hexFrom
		self.hexTo = hexTo
		self.hexStone = hexStone

class RegionType(IntEnum):
	Contested = 0
	Wild = 1
	SettledRed = 2
	SettledWhite = 3
	Stone = 4

class GameState:
	def __init__(self):

		# BB better as single array?
		self.mpHexVik: DefaultDict[Hex, Viking] = defaultdict(lambda:None)
		self.mpHexType: Dict[Hex, RegionType] = {}
		self.mpSideScore = [0,0]

		# self.sideNext = Side.Red # Needed here?
	
	@staticmethod
	def Start():
		"""Initial game state"""

		gs = GameState()
		
		gs.mpHexVik[Hex(5,9)] = Viking(Side.Red, 0)
		gs.mpHexVik[Hex(6,9)] = Viking(Side.Red, 1) 
		gs.mpHexVik[Hex(7,9)] = Viking(Side.Red, 2)
		gs.mpHexVik[Hex(1,0)] = Viking(Side.White, 0)
		gs.mpHexVik[Hex(2,0)] = Viking(Side.White, 1) 
		gs.mpHexVik[Hex(3,0)] = Viking(Side.White, 2)

		for hex in Hex.All():
			gs.mpHexType[hex] = RegionType.Contested

		return gs
	
	@staticmethod
	def HexRoot(mpHexHexParent:DefaultDict[Hex, Hex], hex:Hex) -> Hex:
		hexParent = mpHexHexParent[hex]
		if hexParent != hex:
			hexParent = GameState.HexRoot(mpHexHexParent, hexParent)
			mpHexHexParent[hex] = hexParent
		return hexParent

	def AssignRegions(self:GameState):
		"""Update mpHexType based on connected regions"""

		# Build connectivity graph

		mpHexHexParent:DefaultDict[Hex, Hex] = KeyDependentDefaultDict(lambda hex : hex)
		for hex in Hex.All():
			if self.mpHexType[hex] != RegionType.Contested:
				continue

			hexRoot = self.HexRoot(mpHexHexParent, hex)
		
			for hexOther in hex.Neighbors():
				if self.mpHexType[hexOther] != RegionType.Contested:
					assert(self.mpHexType[hexOther] == RegionType.Stone)
					continue
				hexRootOther = GameState.HexRoot(mpHexHexParent, hexOther)
				mpHexHexParent[hexRootOther] = hexRoot

		mpHexRootSet:DefaultDict[Hex,Set[Hex]] = defaultdict(set)

		for hex in Hex.All(): # BB could I use mpHexHexParent?
			if self.mpHexType[hex] != RegionType.Contested:
				continue
			hexRoot = GameState.HexRoot(mpHexHexParent, hex)

			s = mpHexRootSet[hexRoot]
			s.add(hex)

		for s in mpHexRootSet.values():
			mpSideC = [0,0]

			for hex in s:
				vik = self.mpHexVik[hex]
				if vik != None:
					mpSideC[vik.side] += 1

			typeNew = None

			if mpSideC[Side.Red] == 0:
				if mpSideC[Side.White] == 0:
					typeNew = RegionType.Wild
				else:
					typeNew = RegionType.SettledWhite
					self.mpSideScore[Side.White] += len(s)
			else:
				if mpSideC[Side.White] == 0:
					typeNew = RegionType.SettledRed
					self.mpSideScore[Side.Red] += len(s)
			
			if typeNew:
				for hex in s:
					self.mpHexType[hex] = typeNew

		# scoring functions based on sizes of regions?
	
	def DoMove(self:GameState, move:Move):
		"""Returns a new game state which is result of making the given move"""

		# Copy state
		gs = GameState()
		gs.mpHexVik = copy.copy(self.mpHexVik)
		gs.mpHexType = copy.copy(self.mpHexType)
		gs.mpSideScore = copy.copy(self.mpSideScore)

		# Move viking
		assert(gs.mpHexVik[move.hexFrom] == move.vik)
		del(gs.mpHexVik[move.hexFrom])
		gs.mpHexVik[move.hexTo] = move.vik

		# Place stone
		gs.mpHexType[move.hexStone] = RegionType.Stone

		# Update regions and score
		gs.AssignRegions()

		return gs
	
	def HexesVisibleFrom(self:GameState, hex:Hex, vikIgnore:Viking=None):
		"""Yields all hexes visible from the given hex"""

		for dir in Dir:
			hexNew = hex.Neighbor(dir)
			while hexNew != None: # off edge
				if self.mpHexType[hexNew] == RegionType.Stone:
					break
				vik = self.mpHexVik[hexNew]
				if vik != None and vik != vikIgnore:
					break
				yield hexNew
				hexNew = hexNew.Neighbor(dir)

	def Moves(self:GameState, side:Side):
		"""Yields all legal moves from current state"""

		for hexStart,vik in self.mpHexVik.items():
			if vik.side != side:
				continue
			
			for hexVik in self.HexesVisibleFrom(hexStart):
				for hexStone in self.HexesVisibleFrom(hexVik, vik):
					yield Move(vik, hexVik, hexStone)

class XBoard(Frame):

	xyOffset = 4 #  BB why do I need this? Some sort of non-drawing gutter around edge
	mpSideColor = {Side.Red:"#ff0000", Side.White:"#ffffff"}

	def __init__(self, parent, cX, cY, **kwargs):
		super().__init__(parent, **kwargs)

		self.canvas:Canvas = Canvas(self, width=cX, height=cY, takefocus=True, highlightthickness=0, bg='#c0c0c0')
		self.canvas.grid(column=0, row=0, sticky=(N, W, E, S))

		self.dXSide = 30

		self.dXPerX = self.dXSide * math.sqrt(3)
		self.dXPerY = -self.dXSide * math.sqrt(3) / 2
		self.dYPerY = -self.dXSide * 1.5

		self.xOrigin = 200 # BB compute from others?
		self.yOrigin = 500

		self.dXVikingDot = 40

		self.mpVikIdOval = {}

		self.move:Move = Move(None, None, None, None)
		self.hexesVis = []

		self.fontSize = 30
		self.fontValue = tkFont.Font(family='Helvetica', size=self.fontSize, weight='bold')

		self.BuildHexes()

		self.gsUndoStack:List[GameState] = []
		self.gsRedoStack:List[GameState] = []
		self.SetGameState(GameState.Start())

		self.canvas.bind("<Escape>", self.HandleEscape)
		self.canvas.bind("<<Undo>>", self.HandleUndo)
		self.canvas.bind("<<Redo>>", self.HandleRedo)

		self.canvas.bind("<Button-1>", self.HandleMouseDown)
		self.canvas.bind("<Motion>", self.HandleMouseMove)
		self.canvas.bind("<B1-Motion>", self.HandleMouseDrag)
		self.canvas.bind("<ButtonRelease>", self.HandleMouseUp)

		self.canvas.focus_set()

	def PosCenter(self, hex):
		x = self.xOrigin + (hex.x + 0.5) * self.dXPerX + hex.y * self.dXPerY
		y = self.yOrigin + hex.y * self.dYPerY - self.dXSide / 2
		return (x,y)
	
	def RectViking(self:XBoard, hex:Hex):
		x,y = self.PosCenter(hex)
		return (x - self.dXVikingDot / 2, 
		  		y - self.dXVikingDot / 2,
				x + self.dXVikingDot / 2,
				y + self.dXVikingDot / 2)

	def BuildHexes(self):

		self.mpHexIdPoly = {} # need dict at all?

		canvas = self.canvas

		for hex in Hex.All():
			x = self.xOrigin + hex.x * self.dXPerX + hex.y * self.dXPerY
			y = self.yOrigin + hex.y * self.dYPerY
			id = canvas.create_polygon(
						x, y,
						x + self.dXPerX / 2, y + self.dXSide / 2,
						x + self.dXPerX, y,
						x + self.dXPerX, y - self.dXSide,
						x + self.dXPerX / 2, y - self.dXSide * 1.5,
						x, y - self.dXSide,
						width = 3,
						outline='#000000',
						fill='#FFFFFF')
			self.mpHexIdPoly[hex] = id

	def SetHexColor(self:XBoard, hex:Hex, color):
		self.canvas.itemconfigure(self.mpHexIdPoly[hex], fill=color)
					
	def ResetHexColor(self:XBoard, hex:Hex):
		type = self.gs.mpHexType[hex]
		if type == RegionType.Contested:
			color = '#C0F0C0'
		elif type == RegionType.Wild:
			color = '#C0C0C0'
		elif type == RegionType.SettledWhite:
			color = '#ffffff'
		elif type == RegionType.SettledRed:
			color = '#c00000'
		elif type == RegionType.Stone:
			color = '#202020'
		else:
			assert(False)

		self.SetHexColor(hex, color)

	def SetGameState(self, gs:GameState):
		self.gs:GameState = gs

		for hex,id in self.mpHexIdPoly.items():
			self.ResetHexColor(hex)

		self.canvas.delete("viking")

		for hex,vik in gs.mpHexVik.items():
			if vik == None: # this seems like it should be unnecessary
				continue
			self.mpVikIdOval[vik] = self.canvas.create_oval(
											self.RectViking(hex),
											fill=XBoard.mpSideColor[vik.side],
											tags="viking")
			
		self.canvas.delete("score")
		for side in Side:
			self.canvas.create_text(
								(70 if side == Side.Red else 580, 400), 
								text=f"{gs.mpSideScore[side]}", 
								font=self.fontValue, 
								fill=XBoard.mpSideColor[side],
								tags="score")

	def AppendGameState(self, gs:GameState):
		assert(self.gs != None)
		self.gsUndoStack.append(self.gs)

		self.gsRedoStack = []
		
		self.SetGameState(gs)

	def HexFromEvent(self:XBoard, event:Event):
		for hex,id in self.mpHexIdPoly.items():
			xys = self.canvas.coords(id)
			fInside = True
			for iXy in range(0,len(xys),2):
				x,y = xys[iXy],xys[iXy+1]
				xPrev,yPrev = xys[iXy-2],xys[iXy-1]
				xNormal,yNormal = y - yPrev, xPrev - x
				if event.x * xNormal + event.y * yNormal < x * xNormal + y * yNormal:
					fInside = False
					break
			if fInside:
				return hex
		return None
	
	def UpdateMove(self:XBoard, move:Move):
		if move == None:
			move = Move(None, None, None, None)

		if self.move.vik != None:
			id = self.mpVikIdOval[self.move.vik]
			self.canvas.coords(id, self.RectViking(self.move.hexFrom))
			self.canvas.itemconfigure(id, outline='#000000', width=1)
		for hex in self.hexesVis:
			self.ResetHexColor(hex)

		self.move = move
		if move.vik != None:
			id = self.mpVikIdOval[move.vik]
			self.canvas.itemconfigure(id, outline='#8080ff', width=4)
		  
			if move.hexTo != None:
				self.canvas.coords(id, self.RectViking(move.hexTo))
				self.hexesVis = set(self.gs.HexesVisibleFrom(move.hexTo, move.vik))
			else:
				self.hexesVis = set(self.gs.HexesVisibleFrom(move.hexFrom, move.vik))

			for hex in self.hexesVis:
				self.SetHexColor(hex, '#C0C0ff')

	def HandleMouseDown(self:XBoard, event:Event):
		self.canvas.focus_set()

        # print(f"click at {(event.x, event.y)}")

		hex = self.HexFromEvent(event)
		if hex == None:
			self.UpdateMove(None)
			return
		
		if self.gs.mpHexType[hex] != RegionType.Contested:
			return
		
		fCommand = True if (event.state & 0x8) else False
		# fOption = True if (event.state & 010) else False

		if self.move.vik and hex in self.hexesVis:
			if self.move.hexTo != None:
				# do the move
				move = Move(self.move.vik, self.move.hexFrom, self.move.hexTo, hex)
				self.UpdateMove(None)
				self.AppendGameState(self.gs.DoMove(move))
			else:
				self.UpdateMove(Move(self.move.vik, self.move.hexFrom, hex, None))
			return

		vik = self.gs.mpHexVik[hex]
		if vik:
			# BB enforce alternating sides
			self.UpdateMove(Move(vik, hex, None, None))
			return
		
		self.UpdateMove(None)


	def HandleMouseMove(self, event):
		hex = self.HexFromEvent(event)
		if hex == None:
			return
		# draw circle where we'll move to
		# draw where we'll place stone
		# draw number of hexes in region under 
		pass

	def HandleMouseDrag(self, event):
		pass

	def HandleMouseUp(self, event):
		pass

	def HandleEscape(self, event):
		# Clear move in progress
		self.UpdateMove(None)

	def HandleUndo(self, *args):
		if len(self.gsUndoStack) == 0:
			self.bell()
			return
		
		self.gsRedoStack.append(self.gs)
		self.SetGameState(self.gsUndoStack.pop())

	def HandleRedo(self, *args):
		if len(self.gsRedoStack) == 0:
			self.bell()
			return
		
		self.gsUndoStack.append(self.gs)
		self.SetGameState(self.gsRedoStack.pop())

Hex.Init()

root = Tk()
root.option_add('*tearOff', False)
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

# mainframe = ttk.Frame(root, padding="3 3 12 12")
mainframe = ttk.Frame(root)
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))


xboard = XBoard(mainframe, 650, 550)
xboard.grid(column=0, row=0, sticky=(N, W, E, S))
xboard.winfo_toplevel().title("Ragnarocks")



root.mainloop()