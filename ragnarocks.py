from __future__ import annotations

from tkinter import *
from tkinter import ttk
# from tkFont import *
import tkinter.font as tkFont
import tkinter.filedialog
import tkinter.messagebox
from tkinter import scrolledtext 
from time import *
from collections import defaultdict
import bisect
from typing import Any 
import pyclip
import math

from enum import Enum

class Dir(Enum):
	NW = 0
	NE = 1
	E = 2
	SE = 3
	SW = 4
	W = 5

class Hex:
	s_mpDirDxDy = [(0,1), (1,1), (1,0), (0,-1), (-1,-1), (-1,0)]
	s_mpXYHex = defaultdict(None)

	@staticmethod
	def Init():
		rowdefs = [(0,5), (0,6), (0,7), (0,8), (0,9), (0,10), (0,11), (0,11), (1,10), (2,9)]
		for y,(xMic,c) in enumerate(rowdefs):
			for x in range(xMic, xMic + c):
				Hex.s_mpXYHex[(x,y)] = Hex(x,y)

	def __init__(self, x, y):
		self.x = x  # E from lower left
		self.y = y  # NW from lower left

	@staticmethod
	def Find(x, y):
		return Hex.s_mpXYHex[(x,y)]

	@staticmethod
	def All():
		return Hex.s_mpXYHex.values()

	def Neighbor(self, dir):
		dX,dY = Hex.s_mpDirDxDy[dir]
		return Hex.s_mpXYHex[(self.x + dX, self.y + dY)]

	def Neighbors(self):
		# BB cache this?

		hexes = []
		for dir in Dir:
			hex = self.Neighbor(dir)
			if hex !=  None:
				hexes.append(hex)
		return hexes

class Side(Enum):
	Red = 0
	White = 1 # "Ivory" in official rules

class Viking:
	def __init__(self, side, i):
		self.side = side
		self.i = i # needed at all?

class Move:
	def __init__(self, vik, hexMove, hexStone):
		self.vik = vik
		self.hexMove = hexMove
		self.hexStone = hexStone

class RegionType(Enum):
	Contested = 0
	Wild = 1
	SettledRed = 2
	SettledWhite = 3
	Stone = 4

class GameState:
	def __init__(self):
		self.mpVikHex = {} # list more efficient?
		self.mpXYType = {}
	
	@staticmethod
	def Start():
		gs = GameState()
		gs.mpVikHex[Viking(Side.Red, 0)] = Hex.Find(5,9)
		gs.mpVikHex[Viking(Side.Red, 1)] = Hex.Find(6,9)
		gs.mpVikHex[Viking(Side.Red, 2)] = Hex.Find(7,9)
		gs.mpVikHex[Viking(Side.White, 0)] = Hex.Find(1,0)
		gs.mpVikHex[Viking(Side.White, 1)] = Hex.Find(2,0)
		gs.mpVikHex[Viking(Side.White, 2)] = Hex.Find(3,0)

		for hex in Hex.All():
			gs.mpXYType[(hex.x, hex.y)] = RegionType.Contested

		return gs

class XBoard(Frame):

	xyOffset = 4 #  BB why do I need this? Some sort of non-drawing gutter around edge

	def __init__(self, parent, cX, cY, **kwargs):
		super().__init__(parent, **kwargs)

		self.canvas = Canvas(self, width=cX, height=cY, takefocus=True, highlightthickness=0)
		self.canvas.grid(column=0, row=0, sticky=(N, W, E, S))

		self.dXSide = 30

		self.dXPerX = self.dXSide * math.sqrt(3)
		self.dXPerY = -self.dXSide * math.sqrt(3) / 2
		self.dYPerY = -self.dXSide * 1.5

		self.xOrigin = 200 # BB compute from others?
		self.yOrigin = 500

		self.dXVikingDot = 40

		self.DrawHexes()

		self.fontSize = 30
		self.fontValue = tkFont.Font(family='Helvetica', size=self.fontSize, weight='bold')

		self.canvas.focus_set()

	def PosCenter(self, hex):
		x = self.xOrigin + (hex.x + 0.5) * self.dXPerX + hex.y * self.dXPerY
		y = self.yOrigin + hex.y * self.dYPerY - self.dXSide / 2
		return (x,y)

	def DrawHexes(self):

		self.mpXYIdPoly = {} # need dict at all?

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
			self.mpXYIdPoly[(hex.x,hex.y)] = id

	def SetGameState(self, gs):
		self.m_gs = gs

		for (x,y),id in self.mpXYIdPoly.items():
			type = gs.mpXYType[(x,y)]
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

			self.canvas.itemconfigure(id, fill=color)

		self.canvas.delete("viking")

		mpSideColor = {Side.Red:"#ff0000", Side.White:"#ffffff"}

		for vik,hex in gs.mpVikHex.items():
			x,y = self.PosCenter(hex)
			id = self.canvas.create_oval(
				(x - self.dXVikingDot / 2, y - self.dXVikingDot / 2,
				 x + self.dXVikingDot / 2, y + self.dXVikingDot / 2),
								fill=mpSideColor[vik.side],
								tags="viking")
			# id = self.canvas.create_text(
			# 					self.PosCenter(hex), 
			# 					text='V', 
			# 					font=self.fontValue, 
			# 					fill=mpSideColor[vik.side],
			# 					tags="viking")



#williamrockenbeck@Bills-New-MacBook-Air xword %  /usr/bin/env /usr/local/bin/python3 /Users/williamrockenbeck/.vscode/extensions/ms-python.debugpy-2025.8.0-da
#rwin-arm64/bundled/libs/debugpy/adapter/../../debugpy/launcher 52449 -- /Users/williamrockenbeck/Documents/Python/xword/xword.py 

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

xboard.SetGameState(GameState.Start())


root.mainloop()