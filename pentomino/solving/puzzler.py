'''Hier sind die Funktionen, die das Puzzle lösen wollen.

'''
import random
import time

from pentomino.solving.perfproxy import print_it, TimeIt, is_enabled
from pentomino.pento import get_pentominos
from pentomino.solving import morph
from pentomino.solving import matchstone
from pentomino.solving import resp_puzzler as resp
from pentomino.solving.cntl    import PuzzlerCntl

PENTOMINOES = get_pentominos()

class Puzzler():
    ''' Das ist die Class, in der die Probiererei implementiert ist.
    '''
    def __init__(self, space):
        self.space = space

        self.availables = None
        self.all_stones = None
        to_be_placed = sum((space == 0).flatten()) // 5
        self.cntl = PuzzlerCntl(to_be_placed=to_be_placed)

        self.solutions = 0

        self.solver = self.solve()
        _ = self.solver.send(None)

    def go(self):
        ''' weiter '''
        try:
            with TimeIt('next solver'):
                response = next(self.solver)
            if is_enabled():
                print_it(header=response)
        except StopIteration:
            response = resp.finish('exhausted')
        return response

    def adjust_interrupt(self, down):
        ' Anpassung der Intervall-Länge der Interrupts '
        return self.cntl.adjust_interrupt(down)

    def stop(self):
        ''' Interrupt solve() by setting timeout to zero
        '''
        self.cntl.timeout_before_stop = self.cntl.timeout
        self.cntl.timeout = 0

    def reset_timeout(self):
        ''' reset to timeout 
        '''
        self.cntl.timeout = self.cntl.timeout_before_stop

    def solve(self, shuffle=True):
        '''Tries to fill <space> with pentomino stones.
        '''
        #
        # Es können bereits Steine vorbelegt sein, die nehmen wir jetzt
        # natürlich raus bei der Liste der zu legenden Steine
        #
        stones_in_space = {
            chr(stone) for stone in set(self.space.flatten()) if stone > 0
        }
        shuffled_stones = list(set(PENTOMINOES.keys()) - stones_in_space)

        if shuffle:
            random.shuffle(shuffled_stones)
        else:
            shuffled_stones = 'TFPUXNWLIVYZ'

        size, begin = morph.check_holes(self.space)

        yield resp.interrupt('PRIMED')

        if size is None:
            yield resp.finish('alles gefüllt')
            return
        if size%5 > 0:
            yield resp.finish('Krummes Loch!')
            return

        for gen_resp in self.place_stones(
               shuffled_stones,
               at_pos=begin
               ):
            yield gen_resp
            self.cntl.start = time.time()


    def place_stones(self, stones,  at_pos=None):
        '''Generator: Starte mit an Position <at_pos>
        '''
        self.availables = [True for _ in stones]
        self.all_stones = ''.join(stones)
        self.cntl.start = time.time()

        for resp_gen in self.try_stone(at_pos):
            if resp_gen.is_undo():
                continue
            yield resp_gen
            self.cntl.start = time.time()

    def try_stone(self, at_pos):
        ''' Generator: Try to place stones at position (recursive)
            yields with INTERRUPT or FINISH or ABEND 
        '''

        self.cntl.cnt_placing += 1

        index_stone = self.availables.index(True)

        while True:
            stone = self.all_stones[index_stone]

            positions = matchstone.get_good_posis(
                PENTOMINOES[stone].positions + at_pos,
                self.space)

            new_time = time.time()
            if new_time > self.cntl.start + self.cntl.timeout:    # Sekunden
                self.cntl.cum_placing += self.cntl.cnt_placing
                self.cntl.cnt_placing = 0
                yield resp.interrupt(
                    f'timeout after {self.cntl.cum_placing} tries'
                )
                self.cntl.start = time.time()
                # Hier geht es weiter!

            for position in positions:
                where = tuple(position) # shape (3,5)
                self.space[where] = ord(stone)
                self.cntl.to_be_placed -= 1
                size, next_pos = morph.check_holes(self.space)

                if size  is None:       # Fertig, alles voll
                    self.solutions += 1
                    yield resp.solution(
                        f'Solution {self.solutions} '
                        f'after {self.cntl.cum_placing} tries'
                    )

                elif size%5 == 0:
                    # keine fehlerhaften Löcher, setze nächsten Stein
                    self.availables[index_stone] = False

                    if self.cntl.to_be_placed == self.cntl.prompt_when:
                        avail = ', '.join(
                            stone for available, stone in zip(
                                self.availables, self.all_stones
                            ) if available
                        )
                        yield resp.interrupt(
                            f'Almost finished? Available {avail}'
                        )
                    for response in self.try_stone(at_pos=next_pos):
                        yield response
                else:
                    pass
                # Wenn es hier nun weitergehen soll,
                # muss der letzte Stein zurückgenommen werden:
                self.space[where] = 0
                self.availables[index_stone] = True
                self.cntl.to_be_placed += 1
                # nächste Position

            # alle Positionen ausprobiert, go to next available Stone
            try:
                index_stone = self.availables.index(True, index_stone + 1)
            except ValueError:
                break

        yield resp.undo('try_stone: gaveup')
