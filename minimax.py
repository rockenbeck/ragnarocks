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
	def Score(self) -> float:
		"""Return an estimate for "how good" this state is for the current player"""
		# BB assuming that scores alternate pos/neg as in 2-player game
		#  How to generalize to N-player games?
		pass

	@abstractmethod
	def ScoreNoMoves(self) -> float:
		"""Return score given that there are no possible moves"""
		pass

cScore = 0
def Minimax(gs:AbstractGameState, lookahead:int = 4):
	"""Returns the best move and estimated score for the game state after lookahead moves"""
	# """Returns the best move (min or max depending on flag), and the estimated score for that move after lookahead moves"""
	# BB Need to pass best score possible other ways for better pruning
	#  How does the fancy pruning thing work again?

	global cScore

	scoreBest = None
	moveBest = None
	for move in gs.Moves():
		gsNext = gs.DoMove(move)

		if lookahead > 0:
			moveNext,scoreNext = Minimax(gsNext, lookahead - 1)
			score = -scoreNext
		else:
			cScore += 1
			score = -gsNext.Score()

		if moveBest == None or score > scoreBest:
			scoreBest = score
			moveBest = move
			if scoreBest == sys.float_info.max:
				break
	
	if moveBest == None: # no possible moves -- score is for current game state
		scoreBest = gs.ScoreNoMoves()

	return moveBest,scoreBest
