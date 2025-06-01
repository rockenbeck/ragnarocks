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


class Board:
	def __init__(self:Board, boardlayout:BoardLayout):

		self.boardlayout = boardlayout

		self.mpHexI:Dict[Hex,int] = {}
		self.hexes:List[Hex] = []

		for y,(xMic,c) in enumerate(boardlayout.rowdefs):
			for x in range(xMic, xMic + c):
				hex = Hex(x,y)
				self.mpHexI[hex] = len(self.hexes)
				self.hexes.append(hex)

		self.mpIHexIDirNeighbor:List[List[int]] = []
		self.mpIHexNeighbors:List[List[int]] = []
		for hex in self.hexes:
			mpIDirN = []
			ns = []
			for dir in Dir:
				dX,dY = Hex.s_mpDirDxDy[dir]
				hexOther = Hex(hex.x + dX, hex.y + dY)
				if hexOther in self.mpHexI:
					iHexOther = self.mpHexI[hexOther]
					ns.append(iHexOther)
					mpIDirN.append(iHexOther)
				else:
					mpIDirN.append(None)

			self.mpIHexNeighbors.append(ns)
			self.mpIHexIDirNeighbor.append(mpIDirN)

	def Hexes(self) -> List[Hex]:
		return self.hexes

	def Hex(self, iHex:int) -> Hex:
		return self.hexes[iHex]
	
	def IHex(self, hex:Hex) -> int:
		return self.mpHexI[hex]

	def Neighbor(self, iHex:int, dir:Dir):
		return self.mpIHexIDirNeighbor[iHex][dir]

	def Neighbors(self, iHex:int):
		return self.mpIHexNeighbors[iHex]


class Move:
	def __init__(self, vik, iHexFrom, iHexTo, iHexStone):
		self.vik = vik
		self.iHexFrom = iHexFrom
		self.iHexTo = iHexTo
		self.iHexStone = iHexStone


class RegionType(IntEnum):
	Contested = 0
	Wild = 1
	SettledRed = 2
	SettledWhite = 3
	Stone = 4

class Region():
	def __init__(self):
		self.type = RegionType.Contested
		self.aiHex = []
		self.mpSideCVik = [0,0]


class GameState(AbstractGameState):

	def __init__(self:GameState, board:Board = None, gsPrev:GameState = None, move:Move = None):

		self.regions: List[Region] = []
	
		if board != None:
			# Set up initial board state

			assert(gsPrev == None)
			assert(move == None)

			self.board = board

			self.mpIHexVik: Dict[int, Viking] = {}

			for side in Side:
				for x,y in board.boardlayout.startingPositions[side]:
					self.mpIHexVik[board.IHex(Hex(x,y))] = Viking(side)

			self.mpIHexType: List[int, RegionType] = [RegionType.Contested] * len(board.Hexes())

			self.sideToPlay:Side = Side.Red # Make this a parameter? Or like chess, red always starts

		elif gsPrev:
			# Set up from previous board state + move

			assert(move != None)

			assert(move.vik.side == gsPrev.sideToPlay)

			# Copy state
			# BB better to alter, then undo?
			self.board = gsPrev.board
			self.mpIHexVik = copy.copy(gsPrev.mpIHexVik)
			self.mpIHexType = copy.copy(gsPrev.mpIHexType)

			# Keep uncontested regions from prev; AssignRegions only updates contested ones
			self.regions = list(filter(lambda region: region.type != RegionType.Contested, gsPrev.regions))

			# Move viking
			assert(self.mpIHexVik[move.iHexFrom] == move.vik)
			del(self.mpIHexVik[move.iHexFrom])
			self.mpIHexVik[move.iHexTo] = move.vik

			# Place stone
			self.mpIHexType[move.iHexStone] = RegionType.Stone

			# Alternate sides
			self.sideToPlay = gsPrev.sideToPlay.Opposite()

		# Update regions and score
		self.AssignRegions()
	
	@staticmethod
	def IHexRoot(mpIHexIHexParent:DefaultDict[int, int], iHex:int) -> int:
		iHexParent = mpIHexIHexParent[iHex]
		if iHexParent != iHex:
			iHexParent = GameState.IHexRoot(mpIHexIHexParent, iHexParent)
			mpIHexIHexParent[iHex] = iHexParent
		return iHexParent

	def AssignRegions(self:GameState):
		"""Update mpIHexType and regions based on connected regions"""

		# Build connectivity graph

		mpIHexIHexParent:DefaultDict[int, int] = KeyDependentDefaultDict(lambda iHex : iHex)
		for iHex in range(len(self.board.Hexes())):
			if self.mpIHexType[iHex] != RegionType.Contested:
				continue

			iHexRoot = GameState.IHexRoot(mpIHexIHexParent, iHex)
		
			for iHexOther in self.board.Neighbors(iHex):
				if self.mpIHexType[iHexOther] != RegionType.Contested:
					assert(self.mpIHexType[iHexOther] == RegionType.Stone)
					continue
				iHexRootOther = GameState.IHexRoot(mpIHexIHexParent, iHexOther)
				mpIHexIHexParent[iHexRootOther] = iHexRoot

		mpIHexRootRegion:DefaultDict[int,Region] = defaultdict(lambda : Region())

		for iHex,type in enumerate(self.mpIHexType):
			if type != RegionType.Contested:
				continue
			iHexRoot = GameState.IHexRoot(mpIHexIHexParent, iHex)

			region = mpIHexRootRegion[iHexRoot]
			region.aiHex.append(iHex)
			
			if iHex in self.mpIHexVik:
				vik = self.mpIHexVik[iHex]
				region.mpSideCVik[vik.side] += 1

		for region in mpIHexRootRegion.values():

			typeNew = None

			if region.mpSideCVik[Side.Red] == 0:
				if region.mpSideCVik[Side.White] == 0:
					region.type = RegionType.Wild
				else:
					region.type = RegionType.SettledWhite
			else:
				if region.mpSideCVik[Side.White] == 0:
					region.type = RegionType.SettledRed
				else:
					assert(region.type == RegionType.Contested)
			
			if region.type != RegionType.Contested:
				for iHex in region.aiHex:
					self.mpIHexType[iHex] = region.type

			self.regions.append(region)

		self.mpTypeCHex = [0,0,0,0,0]
		
		for region in self.regions:
			self.mpTypeCHex[region.type] += len(region.aiHex)

		if self.mpTypeCHex[RegionType.Contested] == 0:
			self.sideToPlay = None # done

	def DoMove(self:GameState, move:Move) -> GameState:
		"""Returns a new game state which is result of making the given move"""

		return GameState(gsPrev=self, move=move)
	
	def HexesVisibleFrom(self:GameState, iHex:int, vikIgnore:Viking=None) -> Iterator[Hex]:
		"""Yields all hexes visible from the given hex"""

		for dir in Dir:
			iHexNew = self.board.Neighbor(iHex, dir)
			while iHexNew != None: # off edge
				if self.mpIHexType[iHexNew] == RegionType.Stone:
					break
				if iHexNew in self.mpIHexVik:
					vik = self.mpIHexVik[iHexNew]
					if vik != vikIgnore:
						break
				yield iHexNew
				iHexNew = self.board.Neighbor(iHexNew, dir)

	def Moves(self:GameState) -> Iterator[Move]:
		"""Yields all legal moves from current state"""

		# BB alpha-beta minimax works faster if better moves are yielded first
		#  My instinct is that moving further is usually better -- sort

		for iHexFrom,vik in self.mpIHexVik.items():
			# BB consider other structures for keeping track of vikings
			if vik.side != self.sideToPlay:
				continue
			if self.mpIHexType[iHexFrom] != RegionType.Contested:
				continue
			
			for iHexTo in self.HexesVisibleFrom(iHexFrom):
				for iHexStone in self.HexesVisibleFrom(iHexTo, vikIgnore=vik):
					yield Move(vik, iHexFrom, iHexTo, iHexStone)

	def ScoreEstimate(self:GameState, gameOver:bool=False) -> float:
		"""Return a heuristic value of this board position with higher scores being better for Red"""

		# BB more efficient to calculate score in AssignRegions and not keep stuff around?

		mpTypeCHex = [0,0,0,0,0]
		for region in self.regions:
			mpTypeCHex[region.type] += len(region.aiHex)

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
		for region in self.regions:
			if region.type == RegionType.Contested:
				# frac = region.mpSideCVik[Side.Red] / sum(region.mpSideCVik)

				# check total number of open positions each side can move to
				mpSideCHexVis = [0,0]
				for iHex,vik in self.mpIHexVik.items():
					# Any faster to have bespoke function?
					mpSideCHexVis[vik.side] += sum(1 for _ in self.HexesVisibleFrom(iHex))

				if sum(mpSideCHexVis) > 0: # else neither has any moves?
					# Assign contested hexes based on fraction of open moves
					# Should maybe make cHex smaller because each following
					#  move will reduce total possible area by one
					frac = mpSideCHexVis[Side.Red] / sum(mpSideCHexVis)
					cHex = len(region.aiHex) - 1
					cHexMaybe += Lerp(-cHex, cHex, frac)

		return cHexRed - cHexWhite + cHexMaybe

	def ScoreEstimateNoMoves(self:GameState) -> float:
		return self.ScoreEstimate(gameOver=True)

	def MpSideScore(self:GameState) -> List[int]:
		mpSideScore = [0,0]
		for region in self.regions:
			if region.type == RegionType.SettledRed:
				mpSideScore[Side.Red] += len(region.aiHex)
			elif region.type == RegionType.SettledWhite:
				mpSideScore[Side.White] += len(region.aiHex)
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
		self.hexesVis:List[int] = []

		self.fontSize = 30
		self.fontValue = tkFont.Font(family='Helvetica', size=self.fontSize, weight='bold')

		self.mpIHexIdPoly:List[int] = []
		for iHex in range(len(self.gs.board.Hexes())):
			self.mpIHexIdPoly.append(self.CreateHex(iHex))

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

	def PosCenter(self:RagnarokWidget, iHex:int):
		hex = self.gs.board.Hex(iHex)
		x = self.xOrigin + (hex.x + 0.5) * self.dXPerX + hex.y * self.dXPerY
		y = self.yOrigin + hex.y * self.dYPerY - self.dXSide / 2
		return (x,y)
	
	def RectViking(self:RagnarokWidget, iHex:int):
		x,y = self.PosCenter(iHex)
		return (x - self.dXVikingDot / 2, 
		  		y - self.dXVikingDot / 2,
				x + self.dXVikingDot / 2,
				y + self.dXVikingDot / 2)

	def CreateHex(self:RagnarokWidget, iHex:int, fill='#FFFFFF', tags=None) -> int:
			hex = self.gs.board.Hex(iHex)
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

	def SetHexColor(self:RagnarokWidget, iHex:int, color):
		self.canvas.itemconfigure(self.mpIHexIdPoly[iHex], fill=color)
					
	def ResetHexColor(self:RagnarokWidget, iHex:int):
		type = self.gs.mpIHexType[iHex]
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

		self.SetHexColor(iHex, color)

	def SetGameState(self, gs:GameState):
		assert(gs.board == self.gs.board)
		self.gs = gs

		for iHex in range(len(self.mpIHexIdPoly)):
			self.ResetHexColor(iHex)

		self.canvas.delete("viking")

		for iHex,vik in gs.mpIHexVik.items():
			self.mpVikIdOval[vik] = self.canvas.create_oval(
											self.RectViking(iHex),
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

	def IHexFromEvent(self:RagnarokWidget, event:Event):
		for iHex,id in enumerate(self.mpIHexIdPoly):
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
				return iHex
		return None
	
	def UpdateMove(self:RagnarokWidget, move:Move):
		if move == None:
			move = Move(None, None, None, None)

		self.canvas.delete("move")

		if self.move.vik != None:
			id = self.mpVikIdOval[self.move.vik]
			self.canvas.coords(id, self.RectViking(self.move.iHexFrom))
			self.canvas.itemconfigure(id, outline='#000000', width=1)
		for iHex in self.hexesVis:
			self.ResetHexColor(iHex)

		self.move = move
		if move.vik != None:
			id = self.mpVikIdOval[move.vik]
			self.canvas.itemconfigure(id, outline='#8080ff', width=4)
		  
			if move.iHexTo != None:
				self.canvas.coords(id, self.RectViking(move.iHexTo))
				self.hexesVis = list(self.gs.HexesVisibleFrom(move.iHexTo, move.vik))
			else:
				self.hexesVis = list(self.gs.HexesVisibleFrom(move.iHexFrom, move.vik))

			for iHex in self.hexesVis:
				self.SetHexColor(iHex, '#C0C0ff')

	def HandleMouseDown(self:RagnarokWidget, event:Event):
		self.canvas.focus_set()

        # print(f"click at {(event.x, event.y)}")

		iHex = self.IHexFromEvent(event)
		if iHex == None:
			self.UpdateMove(None)
			return
		
		if self.gs.mpIHexType[iHex] != RegionType.Contested:
			return
		
		fCommand = True if (event.state & 0x8) else False
		# fOption = True if (event.state & 010) else False

		if self.move.vik and iHex in self.hexesVis:
			if self.move.iHexTo != None:
				# do the move
				move = Move(self.move.vik, self.move.iHexFrom, self.move.iHexTo, iHex)
				self.UpdateMove(None)
				self.AppendGameState(self.gs.DoMove(move))
			else:
				self.UpdateMove(Move(self.move.vik, self.move.iHexFrom, iHex, None))
			return

		if iHex in self.gs.mpIHexVik:
			vik = self.gs.mpIHexVik[iHex]
			if vik.side == self.gs.sideToPlay:
				self.UpdateMove(Move(vik, iHex, None, None))
				return
			self.bell() # clicked on wrong side's viking
		
		self.UpdateMove(None)

	def HandleMouseMove(self, event):
		iHex = self.IHexFromEvent(event)
		if iHex == None:
			return
		
		self.canvas.delete("move")
		if self.move.vik and iHex in self.hexesVis:
			if self.move.iHexTo == None:
				# draw viking where we'll move to
				self.canvas.create_oval(
								self.RectViking(iHex),
								fill=RagnarokWidget.mpSideColor[self.move.vik.side],
								tags="move")
			else:
				# draw where we'll place stone
				self.CreateHex(iHex, fill='#808080', tags="move")
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
		# "undo" while move in progress undoes partial move
		if self.move.vik:
			self.CancelMove()
			return

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

bl_Standard = BoardLayout(
				[(0,5), (0,6), (0,7), (0,8), (0,9), (0,10), (0,11), (0,11), (1,10), (2,9)],
				[[(5,9), (6,9), (7,9)], [(1,0), (2,0), (3,0)]])

bl_5x5_3v3 = BoardLayout([(0,4), (0,5), (0,6), (0,7), (0,8), (1,7), (2,6), (3,5), (4,4)], 
						  [[(0,0),(7,4),(4,8)], [(3,0),(0,4),(7,8)]])

# this one is nearly interesting, but starting move is devastating
bl_4x4_2v2 = BoardLayout([(0,4), (0,5), (0,6), (0,7), (1,6), (2,5), (3,4)], [[(3,6), (6,6)], [(0,0),(3,0)]])
# this version is much better
bl_4x4_2v2 = BoardLayout([(0,4), (0,5), (0,6), (0,7), (1,6), (2,5), (3,4)], [[(3,6),(3,0)], [(0,0),(6,6)]])

bl_3x4_2v2 = BoardLayout([(0,4), (0,5), (0,6), (1,5), (2,4)], [[(2,4), (5,4)], [(0,0),(3,0)]])
bl_3x3_2v2 = BoardLayout([(0,3), (0,4), (0,5), (1,4), (2,3)], [[(2,4), (4,4)], [(0,0),(2,0)]])
bl_3x3_1v1 = BoardLayout([(0,3), (0,4), (0,5), (1,4), (2,3)], [[(2,4)], [(0,0)]])
bl_2x2_1v1 = BoardLayout([(0,2), (0,3), (1,2)], [[(2,2)], [(0,0)]])
bl_2x3_1v1 = BoardLayout([(0,3), (0,4), (1,3)], [[(3,2)], [(0,0)]])

board = Board(bl_Standard)
# board = Board(bl_5x5_3v3)
# board = Board(bl_4x4_2v2)
# board = Board(bl_3x4_2v2)
# board = Board(bl_3x3_2v2)
# board = Board(bl_2x2_1v1)
# board = Board(bl_2x3_1v1)

RagnarokWidget = RagnarokWidget(mainframe, GameState(board), 650, 550)
RagnarokWidget.grid(column=0, row=0, sticky=(N, W, E, S))
RagnarokWidget.winfo_toplevel().title("Ragnarocks")



root.mainloop()