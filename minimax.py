from typing import *
from abc import ABC, abstractmethod
import sys



class AbstractGameState(ABC):
	@abstractmethod
	def Moves(self):
		# BB how to hint that it returns new AbstractGameState subclass instances?
		pass

	@abstractmethod
	def DoMove(self, move):
		"""Apply the move to the current game state and returns a new game state"""
		pass

	@abstractmethod
	def ScoreEstimate(self) -> float:
		"""Return an estimate for "how good" this state is for the current player"""
		# BB assuming that scores alternate pos/neg as in 2-player game
		#  How to generalize to N-player games?
		pass

	@abstractmethod
	def ScoreEstimateNoMoves(self) -> float:
		"""Return score given that there are no possible moves"""
		pass

cScore = 0

def MinimaxRecursive(gs:AbstractGameState, fMax:bool, lookahead:int, alpha:float, beta:float):
	"""Minimax with alpha-beta cutoff"""

	global cScore

	if lookahead == 0:
		cScore += 1
		return None, gs.ScoreEstimate()

	moveBest = None
	
	if fMax: # maximizing
		scoreBest = -sys.float_info.max
		for move in gs.Moves():
			gsNext = gs.DoMove(move)

			moveNext,score = MinimaxRecursive(gsNext, False, lookahead - 1, alpha, beta)

			if score > scoreBest:
				scoreBest = score
				moveBest = move

			alpha = max(alpha, score)
			if alpha >= beta:
				break
	else: # minimizing
		scoreBest = sys.float_info.max
		for move in gs.Moves():
			gsNext = gs.DoMove(move)

			moveNext,score = MinimaxRecursive(gsNext, True, lookahead - 1, alpha, beta)

			if score < scoreBest:
				scoreBest = score
				moveBest = move

			beta = min(beta, score)
			if alpha >= beta:
				break
	
	if moveBest == None: # no possible moves -- score is for current game state
		scoreBest = gs.ScoreEstimateNoMoves()

	return moveBest,scoreBest


def Minimax(gs:AbstractGameState, fMax:bool, lookahead:int = 4):
	"""Returns the best move and estimated score for the game state after lookahead moves"""

	return MinimaxRecursive(gs, fMax, lookahead, -sys.float_info.max, sys.float_info.max)