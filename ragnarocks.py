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

from minimax import *



class KeyDependentDefaultDict(defaultdict):
	"""Like DefaultDict, but default_factory takes key as argument"""

	def __missing__(self, key):
		if self.default_factory is None:
			raise KeyError(key)
		else:
			# BB Do I really want to put new one in dict?
			#  Is this how a regular defaultdict behaves?

			ret = self[key] = self.default_factory(key)
			return ret
		
def Lerp(a:float, b:float, alpha:float):
	return (1-alpha) * a + alpha * b



class Dir(IntEnum):
	NW = 0
	NE = 1
	E = 2
	SE = 3
	SW = 4
	W = 5


class Hex:
	s_mpDirDxDy = [(0,1), (1,1), (1,0), (0,-1), (-1,-1), (-1,0)]

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


class Side(IntEnum):
	Red = 0
	White = 1 # "Ivory" in official rules. Save the elephants!

	def Opposite(self:Side) -> Side:
		return Side.Red if self==Side.White else Side.White


class Viking:
	def __init__(self, side):
		self.side = side


class BoardLayout():
	def __init__(self, rowdefs, startingPositions):
		self.rowdefs:List[Tuple[int]] = rowdefs # for each Y, starting X, number of hexes in row
		self.startingPositions:List[List[Tuple[int]]] = startingPositions # for each side, list of starting viking coords

blStandard = BoardLayout(
				[(0,5), (0,6), (0,7), (0,8), (0,9), (0,10), (0,11), (0,11), (1,10), (2,9)],
				[[(5,9), (6,9), (7,9)], [(1,0), (2,0), (3,0)]])

blThreeOnASide1v1 = BoardLayout([(0,3), (0,4), (0,5), (1,4), (2,3)], [[(2,4)], [(0,0)]])
blThreeOnASide2v2 = BoardLayout([(0,3), (0,4), (0,5), (1,4), (2,3)], [[(2,4), (4,4)], [(0,0),(2,0)]])
blTwoOnASide = BoardLayout([(0,2), (0,3), (1,2)], [[(2,2)], [(0,0)]])
blTwoByThree = BoardLayout([(0,3), (0,4), (1,3)], [[(3,2)], [(0,0)]])


class Board:
	def __init__(self:Board, boardlayout:BoardLayout=blStandard):
		self.setHex:Set[Hex] = set()

		self.boardlayout = boardlayout

		for y,(xMic,c) in enumerate(boardlayout.rowdefs):
			for x in range(xMic, xMic + c):
				self.setHex.add(Hex(x,y))

	def __iter__(self):
		return self.setHex.__iter__()

	def Neighbor(self, hex, dir):
		dX,dY = Hex.s_mpDirDxDy[dir]
		hexOther = Hex(hex.x + dX, hex.y + dY)
		return hexOther if hexOther in self.setHex else None

	def Neighbors(self, hex):
		# BB cache this?

		hexes = []
		for dir in Dir:
			hexOther = self.Neighbor(hex, dir)
			if hexOther !=  None:
				hexes.append(hexOther)
		return hexes


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


class GameState(AbstractGameState):

	def __init__(self:GameState, board:Board = None, gsPrev:GameState = None, move:Move = None):

		self.regions: List[Tuple[RegionType, Set[Hex], List[int]]] = []
	
		if board != None:
			assert(gsPrev == None)
			assert(move == None)

			self.board = board

			# BB better as single array?
			self.mpHexVik: Dict[Hex, Viking] = {}
			self.mpHexType: Dict[Hex, RegionType] = {}

			for side in Side:
				for x,y in board.boardlayout.startingPositions[side]:
					self.mpHexVik[Hex(x,y)] = Viking(side)

			for hex in board:
				self.mpHexType[hex] = RegionType.Contested

			self.sideToPlay:Side = Side.Red # Who to start?

		elif gsPrev:
			assert(move != None)

			assert(move.vik.side == gsPrev.sideToPlay)

			# Copy state
			# BB better to alter, then undo?
			self.board = gsPrev.board
			self.mpHexVik = copy.copy(gsPrev.mpHexVik)
			self.mpHexType = copy.copy(gsPrev.mpHexType)
			self.regions = []
			for type,s,mpSideC in gsPrev.regions:
				if type != RegionType.Contested:
					self.regions.append((type,s,mpSideC))

			# Move viking
			assert(self.mpHexVik[move.hexFrom] == move.vik)
			del(self.mpHexVik[move.hexFrom])
			self.mpHexVik[move.hexTo] = move.vik

			# Place stone
			self.mpHexType[move.hexStone] = RegionType.Stone

			# Alternate sides
			self.sideToPlay = gsPrev.sideToPlay.Opposite()

		# Update regions and score
		self.AssignRegions()
	
	@staticmethod
	def HexRoot(mpHexHexParent:DefaultDict[Hex, Hex], hex:Hex) -> Hex:
		hexParent = mpHexHexParent[hex]
		if hexParent != hex:
			hexParent = GameState.HexRoot(mpHexHexParent, hexParent)
			mpHexHexParent[hex] = hexParent
		return hexParent

	def AssignRegions(self:GameState):
		"""Update mpHexType and regions based on connected regions"""

		# Build connectivity graph

		mpHexHexParent:DefaultDict[Hex, Hex] = KeyDependentDefaultDict(lambda hex : hex)
		for hex in self.board:
			if self.mpHexType[hex] != RegionType.Contested:
				continue

			hexRoot = self.HexRoot(mpHexHexParent, hex)
		
			for hexOther in self.board.Neighbors(hex):
				if self.mpHexType[hexOther] != RegionType.Contested:
					assert(self.mpHexType[hexOther] == RegionType.Stone)
					continue
				hexRootOther = GameState.HexRoot(mpHexHexParent, hexOther)
				mpHexHexParent[hexRootOther] = hexRoot

		mpHexRootSet:DefaultDict[Hex,Set[Hex]] = defaultdict(set)

		for hex in self.board: # BB could I use mpHexHexParent?
			if self.mpHexType[hex] != RegionType.Contested:
				continue
			hexRoot = GameState.HexRoot(mpHexHexParent, hex)

			s = mpHexRootSet[hexRoot]
			s.add(hex)

		for s in mpHexRootSet.values():
			mpSideC = [0,0]

			for hex in s:
				if hex in self.mpHexVik:
					vik = self.mpHexVik[hex]
					mpSideC[vik.side] += 1

			typeNew = None

			if mpSideC[Side.Red] == 0:
				if mpSideC[Side.White] == 0:
					typeNew = RegionType.Wild
				else:
					typeNew = RegionType.SettledWhite
			else:
				if mpSideC[Side.White] == 0:
					typeNew = RegionType.SettledRed
				else:
					typeNew = RegionType.Contested
			
			if typeNew != RegionType.Contested:
				for hex in s:
					self.mpHexType[hex] = typeNew

			self.regions.append((typeNew, s, mpSideC))

		self.mpTypeCHex = [0,0,0,0,0]
		
		for type, s, mpSideC in self.regions:
			self.mpTypeCHex[type] += len(s)

		if self.mpTypeCHex[RegionType.Contested] == 0:
			self.sideToPlay = None # done

	def DoMove(self:GameState, move:Move) -> GameState:
		"""Returns a new game state which is result of making the given move"""

		return GameState(gsPrev=self, move=move)
	
	def HexesVisibleFrom(self:GameState, hex:Hex, vikIgnore:Viking=None) -> Iterator[Hex]:
		"""Yields all hexes visible from the given hex"""

		for dir in Dir:
			hexNew = self.board.Neighbor(hex, dir)
			while hexNew != None: # off edge
				if self.mpHexType[hexNew] == RegionType.Stone:
					break
				if hexNew in self.mpHexVik:
					vik = self.mpHexVik[hexNew]
					if vik != vikIgnore:
						break
				yield hexNew
				hexNew = self.board.Neighbor(hexNew, dir)

	def Moves(self:GameState) -> Iterator[Move]:
		"""Yields all legal moves from current state"""

		for hexFrom,vik in self.mpHexVik.items():
			if vik.side != self.sideToPlay:
				continue
			if self.mpHexType[hexFrom] != RegionType.Contested:
				continue
			
			for hexTo in self.HexesVisibleFrom(hexFrom):
				for hexStone in self.HexesVisibleFrom(hexTo, vikIgnore=vik):
					yield Move(vik, hexFrom, hexTo, hexStone)

	def ScoreEstimate(self:GameState, gameOver:bool=False) -> float:
		"""Return a heuristic value of this board position with higher scores being better for Red"""

		# BB more efficient to calculate score in AssignRegions and not keep stuff around?

		mpTypeCHex = [0,0,0,0,0]
		for type, s, mpSideC in self.regions:
			mpTypeCHex[type] += len(s)

		cHexRed = mpTypeCHex[RegionType.SettledRed]
		cHexWhite = mpTypeCHex[RegionType.SettledWhite]

		if gameOver or mpTypeCHex[RegionType.Contested] == 0:
			# game is over
			# BB This counts win as better than possible larger win,
			#  and treats all wins as equal. Could tweak to prefer larger wins

			# if cHexMine > cHexTheirs:
			# 	return sys.float_info.max # win = best possible score
			# elif cHexTheirs > cHexMine:
			# 	return -sys.float_info.max # lose = worst possible score
			# else:
			# 	return 0 # tie

			return (cHexRed - cHexWhite) * 100000

		cHexMaybe = 0 # + for Red, - for White
		for type, s, mpSideC in self.regions:
			if type == RegionType.Contested:
				# frac = mpSideC[Side.Red] / sum(mpSideC)

				mpSideCHexVis = [0,0]
				for hex in s:
					if hex in self.mpHexVik: # BB faster way to compute this?
						vik = self.mpHexVik[hex]
						mpSideCHexVis[vik.side] += sum(1 for _ in self.HexesVisibleFrom(hex))

				if sum(mpSideCHexVis) > 0: # else neither has any moves?
					frac = mpSideCHexVis[Side.Red] / sum(mpSideCHexVis)
					cHex = len(s)
					cHexMaybe += Lerp(-cHex, cHex, frac)

		return cHexRed - cHexWhite + cHexMaybe

	def ScoreEstimateNoMoves(self:GameState) -> float:
		return self.ScoreEstimate(gameOver=True)

	def MpSideScore(self:GameState) -> List[int]:
		mpSideScore = [0,0]
		for type, s, mpSideC in self.regions:
			if type == RegionType.SettledRed:
				mpSideScore[Side.Red] += len(s)
			elif type == RegionType.SettledWhite:
				mpSideScore[Side.White] += len(s)
		return mpSideScore


class RagnarokWidget(Frame):
	"""UI for displaying game state and making moves"""

	xyOffset = 4 #  BB why do I need this? Some sort of non-drawing gutter around edge
	mpSideColor = {Side.Red:"#ff0000", Side.White:"#ffffff"}

	def __init__(self, parent, gs:GameState, cX, cY, **kwargs):
		super().__init__(parent, **kwargs)

		self.gs:GameState = gs

		# BB expose this as options
		self.mpSideFComputer:List[bool] = [False, True]

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
		self.SetGameState(gs)

		self.canvas.bind("<Escape>", self.CancelMove)
		self.canvas.bind("<<Undo>>", self.Undo)
		self.canvas.bind("<<Redo>>", self.Redo)
		self.canvas.bind("c", self.ComputerMove)

		self.canvas.bind("<Button-1>", self.HandleMouseDown)
		self.canvas.bind("<Motion>", self.HandleMouseMove)
		self.canvas.bind("<B1-Motion>", self.HandleMouseDrag)
		self.canvas.bind("<ButtonRelease>", self.HandleMouseUp)

		self.canvas.focus_set()

	def PosCenter(self, hex):
		x = self.xOrigin + (hex.x + 0.5) * self.dXPerX + hex.y * self.dXPerY
		y = self.yOrigin + hex.y * self.dYPerY - self.dXSide / 2
		return (x,y)
	
	def RectViking(self:RagnarokWidget, hex:Hex):
		x,y = self.PosCenter(hex)
		return (x - self.dXVikingDot / 2, 
		  		y - self.dXVikingDot / 2,
				x + self.dXVikingDot / 2,
				y + self.dXVikingDot / 2)

	def CreateHex(self:RagnarokWidget, hex:Hex, fill='#FFFFFF', tags=None) -> int:
			x = self.xOrigin + hex.x * self.dXPerX + hex.y * self.dXPerY
			y = self.yOrigin + hex.y * self.dYPerY
			return self.canvas.create_polygon(
						x, y,
						x + self.dXPerX / 2, y + self.dXSide / 2,
						x + self.dXPerX, y,
						x + self.dXPerX, y - self.dXSide,
						x + self.dXPerX / 2, y - self.dXSide * 1.5,
						x, y - self.dXSide,
						width = 3,
						outline='#000000',
						fill=fill,
						tags=tags)

	def BuildHexes(self):
		self.mpHexIdPoly = {}
		for hex in self.gs.board:
			self.mpHexIdPoly[hex] = self.CreateHex(hex)

	def SetHexColor(self:RagnarokWidget, hex:Hex, color):
		self.canvas.itemconfigure(self.mpHexIdPoly[hex], fill=color)
					
	def ResetHexColor(self:RagnarokWidget, hex:Hex):
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
		assert(gs.board == self.gs.board)
		self.gs = gs

		for hex,id in self.mpHexIdPoly.items():
			self.ResetHexColor(hex)

		self.canvas.delete("viking")

		for hex,vik in gs.mpHexVik.items():
			self.mpVikIdOval[vik] = self.canvas.create_oval(
											self.RectViking(hex),
											fill=RagnarokWidget.mpSideColor[vik.side],
											tags="viking")
			
		self.canvas.delete("score")
		mpSideScore = gs.MpSideScore()
		for side in Side:
			self.canvas.create_text(
								(70 if side == Side.Red else 580, 400), 
								text=f"{mpSideScore[side]}", 
								font=self.fontValue, 
								fill=RagnarokWidget.mpSideColor[side],
								tags="score")

	def AppendGameState(self, gs:GameState):
		assert(self.gs != None)
		self.gsUndoStack.append(self.gs)

		self.gsRedoStack = []
		
		self.SetGameState(gs)

	def HexFromEvent(self:RagnarokWidget, event:Event):
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
	
	def UpdateMove(self:RagnarokWidget, move:Move):
		if move == None:
			move = Move(None, None, None, None)

		self.canvas.delete("move")

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

	def HandleMouseDown(self:RagnarokWidget, event:Event):
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

		if hex in self.gs.mpHexVik:
			vik = self.gs.mpHexVik[hex]
			if vik.side == self.gs.sideToPlay:
				self.UpdateMove(Move(vik, hex, None, None))
				return
			self.bell() # clicked on wrong side's viking
		
		self.UpdateMove(None)

	def HandleMouseMove(self, event):
		hex = self.HexFromEvent(event)
		if hex == None:
			return
		
		self.canvas.delete("move")
		if self.move.vik and hex in self.hexesVis:
			if self.move.hexTo == None:
				# draw viking where we'll move to
				self.canvas.create_oval(
								self.RectViking(hex),
								fill=RagnarokWidget.mpSideColor[self.move.vik.side],
								tags="move")
			else:
				# draw where we'll place stone
				self.CreateHex(hex, fill='#808080', tags="move")
			return

		# draw number of hexes in region under?

	def HandleMouseDrag(self, event):
		pass

	def HandleMouseUp(self, event):
		pass

	def CancelMove(self, *args):
		# Clear move in progress
		self.UpdateMove(None)

	def Undo(self, *args):
		if len(self.gsUndoStack) == 0:
			self.bell()
			return
		
		self.gsRedoStack.append(self.gs)
		self.SetGameState(self.gsUndoStack.pop())

	def Redo(self, *args):
		if len(self.gsRedoStack) == 0:
			self.bell()
			return
		
		self.gsUndoStack.append(self.gs)
		self.SetGameState(self.gsRedoStack.pop())

	def ComputerMove(self, *args):
		move,score = Minimax(self.gs, self.gs.sideToPlay == Side.Red, lookahead=2)
		if move == None:
			self.bell() # no possible moves?
		else:
			self.AppendGameState(self.gs.DoMove(move))



root = Tk()
root.option_add('*tearOff', False)
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

# mainframe = ttk.Frame(root, padding="3 3 12 12")
mainframe = ttk.Frame(root)
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))

# board = Board(blStandard)
board = Board(blThreeOnASide2v2)
# board = Board(blTwoByThree)
# board = Board(blTwoOnASide)

RagnarokWidget = RagnarokWidget(mainframe, GameState(board), 650, 550)
RagnarokWidget.grid(column=0, row=0, sticky=(N, W, E, S))
RagnarokWidget.winfo_toplevel().title("Ragnarocks")



root.mainloop()