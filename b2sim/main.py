# %%
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from b2sim.info import *
import copy

# %%


# %%
def impact(cash, loan, amount):
    #If the amount is positive (like a payment), half of the payment should be directed to the outstanding loan
    #If the amount is negative (like a purchase), then we can treat it "normally"
    if amount > 0:
        if amount > 2*loan:
            cash = cash + amount - loan
            loan = 0
        else:
            cash = cash + amount/2
            loan = loan - amount/2
    else: 
        cash = cash + amount
    return cash, loan

def writeLog(lines, filename = 'log', path = 'logs/'):
    with open(path + filename + '.txt', 'w') as f:
        for line in lines:
            f.write(line)
            f.write('\n')

# %%
class GameState():

    def __init__(self, initial_state):
        
        ############################
        #INITIALIZING THE GAME STATE
        ############################
        
        #Initial cash and eco and loan values
        self.cash = initial_state.get('Cash')
        self.eco = initial_state.get('Eco')
        self.loan = initial_state.get('Loan') #For IMF Loans
        
        #Eco send info
        self.send_name = initial_state.get('Eco Send')
        if self.send_name is None:
            self.send_name = 'Zero'
        
        try:
            self.eco_cost = eco_send_info[self.send_name]['Price']
            self.eco_gain = eco_send_info[self.send_name]['Eco']
            self.eco_time = eco_send_info[self.send_name]['Send Duration']
        except:
            self.send_name = 'Zero'
            self.eco_cost = 0
            self.eco_gain = 0
        
        #~~~~~~~~~~~~~~~~~
        #ROUND LENGTH INFO
        #~~~~~~~~~~~~~~~~~
        
        #Initialize round length info
        self.rounds = initial_state.get('Rounds')
        
        # If the user specifies a starting round instead of a starting time, convert it to a starting time
        # self.current_time is a nonnegative real number telling us how much game time has elapsed
        # self.current_round is an integer telling us what round we're currently on
        # NOTE: In the initial state, the player can specify a decimal value for rounds. A 'Game Round' of 19.5 means "halfway through Round 19" for instance.
        
        if initial_state.get('Game Round') is not None:
            starting_round = initial_state.get('Game Round')
            self.current_time = self.rounds.getTimeFromRound(starting_round)
            self.current_round = int(np.floor(starting_round))
        else:
            self.current_time = initial_state.get('Game Time')
            self.current_round = self.rounds.getRoundFromTime(self.current_time)
        
        #~~~~~~~
        #LOGGING
        #~~~~~~~

        #To ensure the code runs properly, we'll create a log file which the code writes to track what it's doing
        self.logs = []

        #As the Game State evolves, I'll use these arrays to track how cash and eco have changed over time
        self.time_states = [self.current_time]
        self.cash_states = [self.cash] 
        self.eco_states = [self.eco]

        #I'll use this list to track the amount of money each farm makes over the course of the simulation
        self.farm_revenues = []
        self.farm_expenses = []

        #These lists will hold tuples (time, message)
        #These tuples are utilized by the viewCashAndEcoHistory method to display detailed into to the player about what actions were taken at what during simulation
        self.buy_messages = []
        self.eco_messages = []
        
        #~~~~~~~~~~~~~~~
        #FARMS & ALT-ECO
        #~~~~~~~~~~~~~~~
        
        #Process the initial info given about farms/alt-eco:
        
        #Info for whether T5 Farms are up or not
        self.T5_exists = [False, False, False]
        
        #First, farms!

        # We assume in the initial state dictionary that there is an entry "Farms" consisting of a list of dictionaries.
        # Note that the structure of self.farms however is not a list, but a dictionary with keys being nonnegative integers
        # The rationale for doing this is to drastically simplify code related to performing compound transactions.

        self.farms = {}
        farm_info = initial_state.get('Farms')
        self.key = 0
        if farm_info is not None:
            for farm_info_entry in farm_info:
                self.farms[self.key] = MonkeyFarm(farm_info_entry)
                
                #If the farm is a T5 farm, modify our T5 flags appropriately
                #Do not allow the user to initialize with multiple T5's
                for i in range(3):
                    if self.farms[self.key].upgrades[i] == 5 and self.T5_exists[i] == False:
                        self.T5_exists[i] = True
                    elif self.farms[self.key].upgrades[i] == 5 and self.T5_exists[i] == True:
                        self.farms[self.key].upgrades[i] = 4
                
                self.key += 1
        self.farm_revenues = [0 for farm in self.farms]
        self.farm_expenses = [0 for farm in self.farms]

        #Next, boat farms!
        self.boat_farms = initial_state.get('Boat Farms')
        self.Tempire_exists = False
        self.boat_key = 0
        if self.boat_farms is not None:
            for key in self.boat_farms.keys():
                if key >= self.key:
                    self.key = key+1

                boat_farm = self.boat_farms[key]
                #If the boat farm is a Tempire, mark it as such appropriately.
                #Do not allow the user to initialize with multiple Tempires!
                if boat_farm['Upgrade'] == 5 and self.Tempire_exists[i] == False:
                    self.Tempire_exists = True
                elif boat_farm['Upgrade'] == 5 and self.Tempire_exists[i] == True:
                    boat_farm['Upgrade'] = 4

        #Next, druid farms!
        self.druid_farms = initial_state.get('Druid Farms')
        if self.druid_farms is not None:
            self.sotf = self.druid_farms['Spirit of the Forest Index']
            self.druid_key = len(self.druid_farms) - 2
        else:
            self.sotf = None
            self.druid_key = 0

        #Next, supply drops!
        self.supply_drops = initial_state.get('Supply Drops')
        if self.supply_drops is not None:
            self.elite_sniper = self.supply_drops['Elite Sniper Index']
            self.sniper_key = len(self.supply_drops) - 2
        else:
            self.elite_sniper = None
            self.sniper_key = 0

        #Next, heli farms!
        self.heli_farms = initial_state.get('Heli Farms')
        if self.heli_farms is not None:
            self.special_poperations = self.heli_farms['Special Poperations Index']
            self.heli_key = len(self.heli_farms) - 2
        else:
            self.special_poperations = None
            self.heli_key = 0

        #~~~~~~~~~~~~
        #HERO SUPPORT
        #~~~~~~~~~~~~

        self.jericho_steal_time = float('inf') #Represents the time when Jericho's steal is to be activated.
        self.jericho_steal_amount = 25 #Represents the amount of money Jericho steals

        #~~~~~~~~~~~~~~~~
        #THE QUEUE SYSTEM
        #~~~~~~~~~~~~~~~~
        
        #Eco queue info
        
        # Items in the eco_queue look like (time, properties), where properties is a dictionary like so:
        # {
        #     'Send Name': send_name,
        #     'Max Send Amount': max_send_amount,
        #     'Fortified': fortified,
        #     'Camoflauge': camo,
        #     'Regrow': regrow,
        #     'Max Eco Amount': max_eco_amount
        # }

        # Max send amount is useful if we need to simulate sending a precise number of sets of bloons
        # Max eco amount is useful for eco strategies which may demand strategy decisions like "stop eco at 3000 eco"

        self.eco_queue = initial_state.get('Eco Queue')
        self.max_send_amount = initial_state.get('Max Send Amount')
        self.max_eco_amount = initial_state.get('Max Eco Amount')
        self.number_of_sends = 0
        
        #Upgrade queue
        self.buy_queue = initial_state.get('Buy Queue')
        self.buy_cost = None
        self.buffer = 0
        self.min_buy_time = None

        #Attack queue - This is the list of bloons in the center of the screen that pops up whenever you send eco
        self.attack_queue = []
        self.attack_queue_unlock_time = self.current_time
        self.eco_delay = game_globals['Eco Delay']

        #For repeated supply drop buys
        self.supply_drop_max_buy_time = -1
        self.supply_drop_buffer = 0

        #For repeated druid farm buys
        self.druid_farm_max_buy_time = -1
        self.druid_farm_buffer = 0

        #For repeated heli farm buys
        self.heli_farm_max_buy_time = -1
        self.heli_farm_buffer = 0

        #~~~~~~~~~~
        #FAIL-SAFES
        #~~~~~~~~~~
        
        if self.farms is None:
            self.farms = {}
        if self.buy_queue is None:
            self.buy_queue = []
        if self.eco_queue is None:
            self.eco_queue = []
        if self.loan is None:
            self.loan = 0
        if self.boat_farms is None:
            self.boat_farms = {}
        if self.druid_farms is None:
            self.druid_farms = {}
        if self.heli_farms is None:
            self.heli_farms = {}
        if self.supply_drops is None:
            self.supply_drops = {}
            
        self.logs.append("MESSAGE FROM GameState.__init__(): ")
        self.logs.append("Initialized Game State!")
        self.logs.append("The current game round is %s"%(self.current_round))
        self.logs.append("The current game time is %s seconds"%(self.current_time))
        self.logs.append("The game round start times are given by %s \n"%(self.rounds.round_starts))
        
    def viewCashEcoHistory(self, dim = (15,18), display_farms = True):
        self.logs.append("MESSAGE FROM GameState.viewCashEcoHistory():")
        self.logs.append("Graphing history of cash and eco!")

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #Graph the cash and eco values over time
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        fig, ax = plt.subplots(1,2)
        fig.set_size_inches(dim[0],dim[1])
        ax[0].plot(self.time_states, self.cash_states, label = "Cash")
        ax[1].plot(self.time_states, self.eco_states, label = "Eco")
        
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #Mark where the rounds start
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~
        
        cash_min = min(self.cash_states)
        eco_min = min(self.eco_states)
        
        cash_max = max(self.cash_states)
        eco_max = max(self.eco_states)

        round_to_graph = self.rounds.getRoundFromTime(self.time_states[0]) + 1
        while self.rounds.round_starts[round_to_graph] <= self.time_states[-1]:
            ax[0].plot([self.rounds.round_starts[round_to_graph], self.rounds.round_starts[round_to_graph]],[cash_min-1, cash_max+1], label = "R" + str(round_to_graph) + " start", linestyle='dotted', color = 'k')
            ax[1].plot([self.rounds.round_starts[round_to_graph], self.rounds.round_starts[round_to_graph]],[eco_min-1, eco_max+1], label = "R" + str(round_to_graph) + " start", linestyle='dotted', color = 'k')
            round_to_graph += 1

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #Mark where purchases in the buy queue and eco queue occurred
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        for message in self.buy_messages:
            if message[2] == 'Eco':
                line_color = 'b'
            elif message[2] == 'Buy':
                line_color = 'r'

            if len(message[1]) > 30:
                thing_to_say = message[1][0:22] + '...'
            else:
                thing_to_say = message[1]
            
            ax[0].plot([message[0],message[0]],[cash_min-1, cash_max+1], label = thing_to_say, linestyle = 'dashed', color = line_color)
            ax[1].plot([message[0],message[0]],[eco_min-1, eco_max+1], label = thing_to_say, linestyle = 'dashed', color = line_color)

        #~~~~~~~~~~~~~~~~
        #Label the graphs
        #~~~~~~~~~~~~~~~~

        ax[0].set_title("Cash vs Time")
        ax[1].set_title("Eco vs Time")
        
        ax[0].set_ylabel("Cash")
        ax[1].set_ylabel("Eco")
        
        ax[0].set_xlabel("Time (seconds)")
        ax[1].set_xlabel("Time (seconds)")
        
        ax[0].legend(bbox_to_anchor = (1.02, 1))
        ax[1].legend(bbox_to_anchor = (1.02, 1))
        
        fig.tight_layout()

        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        #Create a table that displays the revenue made by each farm
        #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        
        # dictionary of lists 
        if display_farms and len(self.farms) > 0:
            profit = [self.farm_revenues[i] - self.farm_expenses[i] for i in range(len(self.farm_revenues))]
            farm_table = {'Farm Index': [int(i) for i in range(self.key)], 'Revenue': self.farm_revenues, 'Expenses': self.farm_expenses, 'Profit': profit} 
            df = pd.DataFrame(farm_table)
            df = df.set_index('Farm Index')
            df = df.round(0)
            display(df)
        
        self.logs.append("Successfully generated graph! \n")
    
    def changeStallFactor(self,stall_factor):
        #NOTE: This method currently does not see use at all. It may be removed in a future update.
        self.rounds.changeStallFactor(stall_factor,self.current_time)

    def checkProperties(self):
        # Helper method for ecoQueueCorrection.

        #Do not apply modifiers to eco sends if the modifiers are not available
        if self.eco_queue[0]['Time'] < self.rounds.getTimeFromRound(game_globals['Fortified Round']):
            self.eco_queue[0]['Fortified'] = False
        if self.eco_queue[0]['Time'] < self.rounds.getTimeFromRound(game_globals['Camoflauge Round']):
            self.eco_queue[0]['Camoflauge'] = False
        if self.eco_queue[0]['Time'] < self.rounds.getTimeFromRound(game_globals['Regrow Round']):
            self.eco_queue[0]['Regrow'] = False
        
        #Do not apply modifiers to eco sends if they are ineligible to receive such modifiers
        if not eco_send_info[self.eco_queue[0]['Send Name']]['Fortified']:
            self.eco_queue[0]['Fortified'] = False
        if not eco_send_info[self.eco_queue[0]['Send Name']]['Camoflauge']:
            self.eco_queue[0]['Camoflauge'] = False
        if not eco_send_info[self.eco_queue[0]['Send Name']]['Regrow']:
            self.eco_queue[0]['Regrow'] = False

    def ecoQueueCorrection(self):
        # This method automatically adjusts the game state's given eco queue so that it contains valid sends.

        # Essentially, the code works like this:
        # Look at the first send in the queue and decide if the time currently indicated is too early or late, or if we have exceeded the maximum permissible amount of eco for this send (self.max_eco_amount).
        # # If it's too late (we are beyond the last round which we would use the send), remove the send from the queue
        # # If it's too early, adjust the time to earliest available time we can use the send
        # If the process above results in the first send in the queue being slated to be used after the second, *remove* the first send.
        # The process above repeats until either the queue is empty or the first send in the queue is valid.
        # Once it is determined that the first send in the queue is valid, check for and remove any properties from the eco which cannot be applied to said send.

        # When the process above is complete, we must check whether we should change to first send in the queue right now or not.
        # # If the answer is no, we can exit the process.
        # # If the answer is yes, switch to said send, and then (if there are still items in the eco queue) check whether the next item in the send is valid (This entails repeating the *entire* process above!)

        future_flag = False
        while len(self.eco_queue) > 0 and future_flag == False:
            break_flag = False
            while len(self.eco_queue) > 0 and break_flag == False:
                #print("length of queue: %s"%(len(self.eco_queue)))

                #Are we under the eco threshold to use the eco send?
                if self.eco_queue[0]['Max Eco Amount'] is not None and self.eco >= self.eco_queue[0]['Max Eco Amount']:
                    #No, do not use the eco send.
                    self.eco_queue.pop(0)
                else:
                    #Yes, we are under the threshold. Now check if the given time for the send is a valid time..

                    #Is the eco send too late?
                    if self.eco_queue[0]['Time'] >= self.rounds.getTimeFromRound(eco_send_info[self.eco_queue[0]['Send Name']]['End Round']+1):
                        #Yes, the send is too late. Remove it from the queue.
                        self.logs.append("Warning! Time %s is too late to call %s. Removing from eco queue"%(self.eco_queue[0]['Time'],self.eco_queue[0]['Send Name']))
                        self.eco_queue.pop(0)
                        
                    else:
                        #No, the send is not too late
                        
                        #Is the eco send too early?
                        candidate_time = self.rounds.getTimeFromRound(eco_send_info[self.eco_queue[0]['Send Name']]['Start Round'])
                        if self.eco_queue[0]['Time'] < candidate_time:
                            #Yes, the send is too early
                            self.logs.append("Warning! Time %s is too early to call %s. Adjusting the queue time to %s"%(self.eco_queue[0]['Time'],self.eco_queue[0]['Send Name'], candidate_time))
                            self.eco_queue[0] = (candidate_time, self.eco_queue[0]['Send Name'])
                            #Is the adjusted time still valid?
                            if len(self.eco_queue) < 2 or self.eco_queue[0]['Time'] < self.eco_queue[1]['Time']:
                                #Yes, it's still valid
                                self.checkProperties()
                                break_flag = True
                            else:
                                #No, it's not valid
                                self.logs.append("Warning! Time %s is too late to call %s because the next item in the eco queue is slated to come earlier. Removing from eco queue"%(self.eco_queue[0]['Time'],self.eco_queue[0]['Send Name']))
                                self.eco_queue.pop(0)
                        else:
                            #No, the send is not too early
                            self.checkProperties()
                            break_flag = True
            
            if len(self.eco_queue) > 0 and self.eco_queue[0]['Time'] <= self.current_time:
                self.changeEcoSend(self.eco_queue[0])
                self.eco_queue.pop(0)
            else:
                future_flag = True
        
    def changeEcoSend(self,send_info):
        # NOTE: This function does NOT contain safeguards to prevent the player from changing to unavailable eco sends.
        # Such safeguards are handled by the ecoQueueCorrection method, which is automatically run when simulating game states.

        # The send info dictionary looks like this:
        # {
        #     'Time': time,
        #     'Send Name': send_name,
        #     'Max Send Amount': max_send_amount,
        #     'Fortified': fortified,
        #     'Camoflauge': camo,
        #     'Regrow': regrow,
        #     'Max Eco Amount': max_eco_amount
        # }
        
        # First, check if the send has any fortied, camo, or regrow characteristics
        eco_cost_multiplier = 1
        if send_info['Fortified'] == True:
            eco_cost_multiplier *= game_globals['Fortified Multiplier']
        if send_info['Camoflauge'] == True:
            eco_cost_multiplier *= game_globals['Camoflauge Multiplier']
        if send_info['Regrow'] == True:
            eco_cost_multiplier *= game_globals['Regrow Multiplier']

        self.send_name = send_info['Send Name']

        # If an eco send is a MOAB class send, fortifying it doubles the eco penalty
        eco_gain_multiplier = 1
        if eco_send_info[self.send_name]['MOAB Class'] and send_info['Fortified']:
            eco_gain_multiplier = 2

        self.eco_cost = eco_cost_multiplier*eco_send_info[self.send_name]['Price']
        self.eco_gain = eco_gain_multiplier*eco_send_info[self.send_name]['Eco']
        self.eco_time = eco_send_info[self.send_name]['Send Duration']

        #Setting the max_send_amount
        self.max_send_amount = send_info['Max Send Amount']
        self.number_of_sends = 0

        #Setting the max_eco_amount
        self.max_eco_amount = send_info['Max Eco Amount']

        self.logs.append("Modified the eco send to %s"%(self.send_name))
        self.buy_messages.append((self.current_time, 'Change eco to %s'%(self.send_name), 'Eco'))

    def showWarnings(self,warnings):
        for index in warnings:
            print(self.logs[index])
        
    def fastForward(self, target_time = None, target_round = None, interval = 0.1):
        self.logs.append("MESSAGE FROM GameState.fastForward: ")

        #Collect a list of indices corresponding to log messages the player should know about.
        #Useful for when the user inputs incorrect data or gets unexpected results.
        self.warnings = []
        self.valid_action_flag = True #To prevent the code from repeatedly trying to perform a transaction that obviously can't happen
        
        # If a target round is given, compute the target_time from that
        if target_round is not None:
            target_time = self.rounds.getTimeFromRound(target_round)
            
        #A fail-safe to prevent the code from trying to go backwards in time
        if target_time < self.current_time:
            target_time = self.current_time
        
        while self.current_time < target_time:
            intermediate_time = min(max(np.floor(self.current_time/interval + 1)*interval,self.current_time + interval/2),target_time)
            self.logs.append("Advancing game to time %s"%(np.round(intermediate_time,3)))
            self.advanceGameState(target_time = intermediate_time)
            self.logs.append("----------")

        #FOR SPOONOIL: Show warning messages for fail-safes triggered during simulation
        self.showWarnings(self.warnings)
        
        self.logs.append("Advanced game state to round " + str(self.current_round))
        self.logs.append("The current time is " + str(self.current_time))
        self.logs.append("The next round starts at time " + str(self.rounds.round_starts[self.current_round+1]))
        self.logs.append("Our new cash and eco is given by (%s,%s) \n"%(np.round(self.cash,2),np.round(self.eco,2)))

    def advanceGameState(self, target_time = None, target_round = None):
        # self.logs.append("MESSAGE FROM GameState.advanceGameState: ")
        # Advance the game to the time target_time, 
        # computing the new money and eco amounts at target_time

        # NOTE: This function only works so long as nothing about the player's income sources changes.
        # Thus, if the player makes a purchase or changes eco sends, we will terminate prematurely.

        ###################
        #PART 0: FAIL-SAFES
        ###################

        # If the eco queue has the player try to use eco sends when they unavailable, automatically modify the queue so this doesn't happen
        self.ecoQueueCorrection()
        
        # FAIL-SAFE: Terminate advanceGameState early if an eco change is scheduled before the target_time.
        if len(self.eco_queue) > 0 and self.eco_queue[0]['Time'] < target_time:
            #Yes, an eco change will occur
            target_time = self.eco_queue[0]['Time']

        # FAIL-SAFE: Check whether the current eco send is valid. If it is not, change the eco send to zero.
        if eco_send_info[self.send_name]['End Round'] < self.current_round:
            self.logs.append("Warning! The eco send %s is no longer available! Switching to the zero send."%(self.send_name))
            self.warnings.append(len(self.logs) - 1)
            self.changeEcoSend({'Send Name': 'Zero'})

        # FAIL-SAFE: Prevent advanceGameState from using an eco send after it becomes unavailable by terminating early in this case.
        if eco_send_info[self.send_name]['End Round'] + 1 <= self.rounds.getRoundFromTime(target_time):
            target_time = self.rounds.getTimeFromRound(eco_send_info[self.send_name]['End Round'] + 1)
            self.logs.append("Warning! The current eco send will not be available after the conclusion of round %s. Adjusting the target time."%(eco_send_info[self.send_name]['End Round']))

        # FAIL-SAFE: Only try to update if we are trying to go into the future. Do NOT try to go back in time!
        if target_time <= self.current_time:
            self.logs.append("Warning! The target time is in the past! Terminating advanceGameState()")
            self.warnings.append(len(self.logs) - 1)
            return None
        
        ############################################
        #PART 1: COMPUTATION OF PAYOUT TIMES & INFOS
        ############################################
        
        #Entries in payout_times take the format of a dictionary with paramters 'Time' and 'Payment' (if possible).
        
        payout_times = self.computePayoutSchedule(target_time)

        ##############################
        #PART 2: COMPUTATION OF WEALTH
        ##############################
        
        # Now that payouts have been computed and sorted, award them in the order they are meant to be awarded in.
        # The general flow of the code in this part is this:
            # Compute the impact of eco between payments
            # Award payment
            # Try to make purchases immediately after receiving the payment.
        
        made_purchase = False
        for i in range(len(payout_times)):
            payout = payout_times[i]
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #First, compute the impact of eco from the previous payout (or starting time) to the current one
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

            self.updateEco(payout['Time'])

            if (self.max_send_amount is not None and self.number_of_sends == self.max_send_amount) or (self.max_eco_amount is not None and self.eco >= self.max_eco_amount):
                self.logs.append("Reached the limit on eco'ing for this send! Moving to the next send in the queue.")

                if len(self.eco_queue) > 0:
                    self.eco_queue[0]['Time'] = self.current_time
                    self.ecoQueueCorrection()
                else:
                    #Switch to the zero send
                    self.logs.append("No more sends in the eco queue! Switching to the zero send.")
                    self.eco_queue.append({
                        'Time': self.current_time,
                        'Send Name': 'Zero',
                        'Max Send Amount': None,
                        'Max Eco Amount': None,
                        'Fortified': False,
                        'Camoflauge': False,
                        'Regrow': False
                    })
                
                # In rare cases, we may break from the eco queue on exactly same time that we are slated to receive a payment
                # In that rare case, we need to award the payment for that time and check the buy queue to ensure that we do not "skip" over anything essential.
                if self.current_time < payout['Time']:
                    break
                else:
                    made_purchase = True

            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ 
            #Next, award the payout at the given time
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            
            # WARNING! If an IMF Loan is active, half of the payment must go towards the loan.
            
            if payout['Payout Type'] == 'Direct':
                #This case is easy! Just award the payment and move on
                if payout['Source'] != 'Ghost': # To avoid having the "ghost payment" included in the logs
                    new_cash, new_loan = impact(self.cash,self.loan, payout['Payout'])

                    if payout['Source'] == 'Farm':
                        #Track the money generated by the farm
                        key = payout['Index']
                        self.farm_revenues[key] += new_cash - self.cash

                    self.cash, self.loan = new_cash, new_loan
                    self.logs.append("Awarded direct payment %s at time %s"%(np.round(payout['Payout'],2),np.round(payout['Time'],2)))
                
                
            elif payout['Payout Type'] == 'Bank Payment':
                #Identify the bank that we're paying and deposit money into that bank's account
                #NOTE: Bank deposits are not impacted by IMF Loans. It is only when we withdraw the money that the loan is repaid
                key = payout['Index']
                farm = self.farms[key]
                farm.account_value += payout['Payout']
                self.logs.append("Awarded bank payment %s at time %s to farm at index %s"%(np.round(payout['Payout'],2),np.round(payout['Time'],2), key))
                if farm.account_value >= farm.max_account_value:
                    #At this point, the player should withdraw from the bank.
                    farm.account_value = 0
                    new_cash, new_loan = impact(self.cash,self.loan,farm.max_account_value)
                    self.farm_revenues[key] += new_cash - self.cash #Track the money generated by the farm
                    self.cash, self.loan = new_cash, new_loan
                    self.logs.append("The bank at index %s reached max capacity! Withdrawing money"%(key))
                self.logs.append("The bank's new account value is %s"%(farm.account_value))
            elif payout['Payout Type'] == 'Bank Interest':
                #Identify the bank that we're paying and deposit $400, then give 20% interest
                key = payout['Index']
                farm = self.farms[key]
                farm.account_value += 400
                farm.account_value *= 1.2
                self.logs.append("Awarded bank interest at time %s to the farm at index %s"%(np.round(payout['Time'],2), key))
                if farm.account_value >= farm.max_account_value:
                    farm.account_value = 0
                    new_cash, new_loan = impact(self.cash,self.loan,farm.max_account_value)
                    self.farm_revenues[key] += new_cash - self.cash #Track the money generated by the farm
                    self.cash, self.loan = new_cash, new_loan
                    self.logs.append("The bank at index %s reached max capacity! Withdrawing money"%(key))
                self.logs.append("The bank's new account value is %s"%(farm.account_value))
            elif payout['Payout Type'] == 'Eco':
                self.cash, self.loan = impact(self.cash,self.loan, self.eco)
                self.logs.append("Awarded eco payment %s at time %s"%(np.round(self.eco,2),np.round(payout['Time'],2)))
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #Now, check whether we can perform the next buy in the buy queue
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            
            # The simulation should attempt to process the buy queue after every payout, *except* if multiple payouts occur at the same time
            # If multiple payouts occur at the same time, only access the buy queue after the *last* of those payments occurs.

            try_to_buy = False

            if i == len(payout_times)-1:
                try_to_buy = True
            elif payout_times[i]['Time'] < payout_times[i+1]['Time']:
                try_to_buy = True
            
            if try_to_buy:
                if self.processBuyQueue(payout):
                    made_purchase = True
            
            #~~~~~~~~~~~~~~~~~~~~
            # Automated Purchases
            #~~~~~~~~~~~~~~~~~~~~

            # There are actions in actions.py which let the player trigger the action of repeatedly buying supply drops or druid farms.
            # These while loops process *those* transactions independently of the buy queue.
            # WARNING: Unusual results will occur if you attempt to implement automated purchases of multiple alt eco's at the same time.
            # WARNING: Because automated purchases are processed after checking the buy queue, unexpected results may occur if items in the buy queue do not have a min_buy_time designated.

            if payout['Time'] <= self.supply_drop_max_buy_time and try_to_buy == True:
                while self.cash >= sniper_globals['Supply Drop Cost'] + self.supply_drop_buffer:
                    made_purchase = True
                    self.cash -= sniper_globals['Supply Drop Cost']
                    self.supply_drops[self.sniper_key] = payout['Time']
                    self.sniper_key += 1
                    self.logs.append("Purchased a supply drop! (Automated purchase)")

            if payout['Time'] <= self.druid_farm_max_buy_time and try_to_buy == True:
                while self.cash >= druid_globals['Druid Farm Cost'] + self.druid_farm_buffer:
                    made_purchase = True
                    self.cash -= druid_globals['Druid Farm Cost']
                    self.druid_farms[self.druid_key] = payout['Time']
                    self.druid_key += 1
                    self.logs.append("Purchased a druid farm! (Automated purchase)")

            if payout['Time'] <= self.heli_farm_max_buy_time and try_to_buy == True:
                while self.cash >= heli_globals['Heli Farm Cost'] + self.heli_farm_buffer:
                    made_purchase = True
                    self.cash -= heli_globals['Heli Farm Cost']
                    self.heli_farms[self.heli_key] = payout['Time']
                    self.heli_key += 1
                    self.logs.append("Purchased a heli farm! (Automated purchase)")
            
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            #Record the cash & eco history and advance the game time
            #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
            
            #print("New cash and eco is (%s,%s)"%(np.round(self.cash,2), np.round(self.eco,2)))
            self.time_states.append(payout['Time'])
            self.cash_states.append(self.cash)
            self.eco_states.append(self.eco)
            self.logs.append("Recorded cash and eco values (%s,%s) at time %s"%(np.round(self.cash,2),np.round(self.eco,2),np.round(payout['Time'],2)))
            
            # NOTE: The last payment is a "ghost" payment to be awarded at the target time.
            self.current_time = payout['Time']

            #If a purchase occured in the buy queue, exit the processing of payments early
            if made_purchase == True:
                target_time = self.current_time
                break

            #end of for loop
        
        # After going through the for loop, we have accounted for all payments that could occur in the time period of interest
        # and also performed any purchases in our buy queue along the way. 
            
        ####################################
        #PART 3: UPDATE GAME TIME PARAMETERS
        ####################################
        
        # DEVELOPER'S NOTE: The list of payments always includes a "ghost" payment of 0 dollars at the designated target time. That payment helps to simplify this code. 
        self.current_time = target_time

        while self.rounds.round_starts[self.current_round] <= self.current_time:
            self.current_round += 1
        self.current_round -= 1
        
        #Update the eco send, if necessary
        if len(self.eco_queue) > 0 and target_time >= self.eco_queue[0]['Time']:
            self.changeEcoSend(self.eco_queue[0])
            self.eco_queue.pop(0)
        
        #self.logs.append("Advanced game state to round " + str(self.current_round))
        #self.logs.append("The current time is " + str(self.current_time))
        #self.logs.append("The next round starts at time " + str(self.rounds.round_starts[self.current_round+1]))
        #self.logs.append("Our new cash and eco is given by (%s,%s) \n"%(np.round(self.cash,2),np.round(self.eco,2)))
           
    def computePayoutSchedule(self, target_time):
        # Helper method for advanceGameState
        # Given a target time target_time, return an order list of all payouts to occur from the game state's current time until the designated target time.
        # Each entry in the returned array is a dictionary detailing the time the payment is to occur and either the payment to give or instructions to compute that payment (necessary for eco for banks)

        payout_times = []
        
        #ECO PAYOUTS
        eco_time = 6*(np.floor(self.current_time/6)+1)
        while eco_time <= target_time:
            payout_entry = {
                'Time': eco_time,
                'Payout Type': 'Eco'
            }
            payout_times.append(payout_entry)
            eco_time += 6

        #DRUID FARMS
        if self.druid_farms is not None:
            for key in self.druid_farms.keys():
                druid_farm = self.druid_farms[key]

                #Determine the earliest druid farm activation that could occur within the interval of interest (self.current_time,target_time]
                use_index = max(1,np.floor(1 + (self.current_time - druid_farm - druid_globals['Druid Farm Initial Cooldown'])/druid_globals['Druid Farm Usage Cooldown'])+1)
                druid_farm_time = druid_farm + druid_globals['Druid Farm Initial Cooldown'] + druid_globals['Druid Farm Usage Cooldown']*(use_index-1)
                while druid_farm_time <= target_time:
                    payout_entry = {
                        'Time': druid_farm_time,
                        'Payout Type': 'Direct',
                        'Payout': druid_globals['Druid Farm Payout'],
                        'Source': 'Druid'
                    }
                    payout_times.append(payout_entry)
                    druid_farm_time += druid_globals['Druid Farm Usage Cooldown']

                if key == self.sotf:
                    #Spirit of the Forest has a start of round payment of 3000 dollars in addition to the payouts that x4x druids can give out 
                    #At the start of each round, append a payout entry with the SOTF payout
                    self.inc = 1
                    while self.rounds.getTimeFromRound(self.current_round + self.inc) <= target_time:
                        payout_entry = {
                            'Time': self.rounds.getTimeFromRound(self.current_round + self.inc),
                            'Payout Type': 'Direct',
                            'Payout': druid_globals['Spirit of the Forest Bonus'],
                            'Source': 'Druid'
                        }
                        payout_times.append(payout_entry)
                        self.inc += 1


        #SUPPLY DROPS
        if self.supply_drops is not None:
            for key in self.supply_drops.keys():
                supply_drop = self.supply_drops[key]
                if key == self.elite_sniper:
                    payout_amount = sniper_globals['Elite Sniper Payout']
                else:
                    payout_amount = sniper_globals['Supply Drop Payout']

                #Determine the earliest supply drop activation that could occur within the interval of interest (self.current_time,target_time]
                drop_index = max(1,np.floor(1 + (self.current_time - supply_drop - sniper_globals['Supply Drop Initial Cooldown'])/sniper_globals['Supply Drop Usage Cooldown'])+1)
                supply_drop_time = supply_drop + sniper_globals['Supply Drop Initial Cooldown'] + sniper_globals['Supply Drop Usage Cooldown']*(drop_index-1)
                while supply_drop_time <= target_time:
                    
                    payout_entry = {
                        'Time': supply_drop_time,
                        'Payout Type': 'Direct',
                        'Payout': payout_amount,
                        'Source': 'Sniper'
                    }
                    payout_times.append(payout_entry)
                    supply_drop_time += sniper_globals['Supply Drop Usage Cooldown']

        #HELI FARMS
        if self.heli_farms is not None:
            for key in self.heli_farms.keys():
                heli_farm = self.heli_farms[key]
                if key == self.special_poperations:
                    payout_amount = heli_globals['Special Poperations Payout']
                else:
                    payout_amount = heli_globals['Heli Farm Payout']

                #Determine the earliest heli farm usage that could occur within the interval of interest (self.current_time,target_time]
                drop_index = max(1,np.floor(1 + (self.current_time - heli_farm - heli_globals['Heli Farm Initial Cooldown'])/heli_globals['Heli Farm Usage Cooldown'])+1)
                heli_farm_time = heli_farm + heli_globals['Heli Farm Initial Cooldown'] + heli_globals['Heli Farm Usage Cooldown']*(drop_index-1)
                while heli_farm_time <= target_time:
                    
                    payout_entry = {
                        'Time': heli_farm_time,
                        'Payout Type': 'Direct',
                        'Payout': payout_amount,
                        'Source': 'Heli'
                    }
                    payout_times.append(payout_entry)
                    heli_farm_time += heli_globals['Heli Farm Usage Cooldown']

        #FARMS
        if len(self.farms) > 0:
            for key in self.farms.keys():
                farm = self.farms[key]
                #If the farm is a monkeynomics, determine the payout times of the active ability
                if farm.upgrades[1] == 5:
                    farm_time = farm.min_use_time
                    while farm_time <= target_time:
                        if farm_time > self.current_time:
                            payout_entry = {
                                'Time': farm_time,
                                'Payout Type': 'Direct',
                                'Payout': farm_globals['Monkeynomics Payout'],
                                'Source': 'Farm',
                                'Index': key
                            }
                            payout_times.append(payout_entry)
                        farm_time += farm_globals['Monkeynomics Usage Cooldown']
                    farm.min_use_time = farm_time
                
                farm_purchase_round = self.rounds.getRoundFromTime(farm.purchase_time)
                self.inc = 0
                self.flag = False
                while self.flag == False:
                    #If computing farm payments on the same round as we are currently on, precompute the indices the for loop should go through.
                    #NOTE: This is not necessary at the end because the for loop terminates when a "future" payment is reached.
                    if self.inc == 0:
                        if self.current_round > farm_purchase_round:
                            #When the farm was purchased on a previous round
                            round_time = self.current_time - self.rounds.round_starts[self.current_round]
                            loop_start = int(np.floor(farm.payout_frequency*round_time/self.rounds.nat_send_lens[self.current_round]) + 1)
                            loop_end = farm.payout_frequency
                        else: #self.current_round == farm_purhcase_round
                            #When the farm was purchased on the same round as we are currently on
                            loop_start = int(np.floor(farm.payout_frequency*(self.current_time - farm.purchase_time)/self.rounds.nat_send_lens[self.current_round]-1)+1)
                            loop_end = int(np.ceil(farm.payout_frequency*(1 - (farm.purchase_time - self.rounds.round_starts[self.current_round])/self.rounds.nat_send_lens[self.current_round])-1)-1)
                    else:
                        loop_start = 0
                        loop_end = farm.payout_frequency
                    
                    #self.logs.append("Precomputed the loop indices to be (%s,%s)"%(loop_start,loop_end))
                    #self.logs.append("Now computing payments at round %s"%(self.current_round + self.inc))
                    
                    for i in range(loop_start, loop_end):
                        #Precompute the value i that this for loop should start at (as opposed to always starting at 0) to avoid redundant computations
                        #Farm payout rules are different for the round the farm is bought on versus subsequent rounds
                        if self.current_round + self.inc == farm_purchase_round:
                            farm_time = farm.purchase_time + (i+1)*self.rounds.nat_send_lens[self.current_round + self.inc]/farm.payout_frequency
                        else:
                            farm_time = self.rounds.round_starts[self.current_round + self.inc] + i*self.rounds.nat_send_lens[self.current_round + self.inc]/farm.payout_frequency
                        
                        #Check if the payment time occurs within our update window. If it does, add it to the payout times list
                        if farm_time <= target_time and farm_time > self.current_time:
                            
                            #Farm payouts will either immediately be added to the player's cash or added to the monkey bank's account value
                            #This depends of course on whether the farm is a bank or not.
                            
                            #WARNING: If the farm we are dealing with is a bank, we must direct the payment into the bank rather than the player.
                            #WARNING: If the farm we are dealing with is a MWS, we must check whether we are awarding the MWS bonus payment!
                            #WARNING: If the farm we are dealing with is a BRF, we must check whether the BRF buff is being applied or not!
                            
                            if farm.upgrades[1] >= 3:
                                if i == 0 and self.current_round + self.inc > farm_purchase_round:
                                    #At the start of every round, every bank gets a $400 payment and then is awarded 20% interest.
                                    payout_entry = {
                                        'Time': farm_time,
                                        'Payout Type': 'Bank Interest',
                                        'Index': key,
                                        'Source': 'Farm'
                                    }
                                    payout_times.append(payout_entry)
                                payout_entry = {
                                    'Time': farm_time,
                                    'Payout Type': 'Bank Payment',
                                    'Index': key,
                                    'Payout': farm.payout_amount,
                                    'Source': 'Farm'
                                }
                            elif i == 0 and farm.upgrades[2] == 5 and self.current_round + self.inc > farm_purchase_round:
                                payout_entry = {
                                    'Time': farm_time,
                                    'Payout Type': 'Direct',
                                    'Payout': farm.payout_amount + farm_globals['Monkey Wall Street Bonus'],
                                    'Source': 'Farm',
                                    'Index': key
                                }
                            elif farm.upgrades[0] == 4 and self.T5_exists[0] == True:
                                payout_entry = {
                                    'Time': farm_time,
                                    'Payout Type': 'Direct',
                                    'Payout': farm.payout_amount*farm_globals['Banana Central Multplier'],
                                    'Source': 'Farm',
                                    'Index': key
                                }
                            else:
                                payout_entry = {
                                    'Time': farm_time,
                                    'Payout Type': 'Direct',
                                    'Payout': farm.payout_amount,
                                    'Source': 'Farm',
                                    'Index': key
                                }
                            payout_times.append(payout_entry)
                        elif farm_time > target_time:
                            #self.logs.append("The payout time of %s is too late! Excluding payout time!"%(farm_time))
                            self.flag = True
                            break
                    self.inc += 1
        
        #BOAT FARMS
        if len(self.boat_farms) > 0:

            #If the player has Trade Empire, determine the buff to be applied to other boat farm payments
            if self.Tempire_exists == True:
                arg = min(len(self.boat_farms) - 1,20)
            else:
                arg = 0
            multiplier = 1 + 0.05*arg

            #Determine the amount of the money the boats will give each round
            boat_payout = 0
            for key in self.boat_farms.keys():
                boat_farm = self.boat_farms[key]
                boat_payout += multiplier*boat_payout_values[boat_farm['Upgrade'] - 3]

            #At the start of each round, append a payout entry with the boat payout
            self.inc = 1
            while self.rounds.getTimeFromRound(self.current_round + self.inc) <= target_time:
                payout_entry = {
                    'Time': self.rounds.getTimeFromRound(self.current_round + self.inc),
                    'Payout Type': 'Direct',
                    'Payout': boat_payout,
                    'Source': 'Boat',
                }
                payout_times.append(payout_entry)
                self.inc += 1

        #JERICHO PAYOUTS
        jeri_time = self.jericho_steal_time
        while jeri_time <= min(target_time, self.jericho_steal_time + (hero_globals['Jericho Number of Steals']-1)*hero_globals['Jericho Steal Interval']):
            if jeri_time > self.current_time:
                payout_entry = {
                    'Time': jeri_time,
                    'Payout Type': 'Direct',
                    'Payout': self.jericho_steal_amount,
                    'Source': 'Jericho',
                }
                payout_times.append(payout_entry)
            jeri_time += hero_globals['Jericho Steal Interval']

        #GHOST PAYOUT
        #This special payout prevents the code from waiting possibly several seconds to carry out purchases in the buy queue that can obviously be afforded
        payout_entry = {
            'Time': target_time,
            'Payout Type': 'Direct',
            'Payout': 0,
            'Source': 'Ghost',
        }
        payout_times.append(payout_entry)

        #Now that we determined all the payouts, sort the payout times by the order they occur in
        payout_times = sorted(payout_times, key=lambda x: x['Time']) 
        #self.logs.append("Sorted the payouts in order of increasing time!")

        return payout_times

    def updateEco(self, target_time):
        # Helper method which updates eco from the current game time to the specified target_time.
        # self.logs.append("Running updateEco!")

        # DEVELOPER'S NOTE: Because of a shortcoming in the code, if the player runs out of cash in the simulator while eco'ing, 
        # There is a very small delay between when the player earns enough cash to eco again and when they actually start eco'ing again.
        # This shortcoming is due to the fact that, if the player is to receive a payment on the same time that they try to send a set of bloons, the simulator will try to send the bloons first before awarding the payment.
        # There is a known fix for this issue, but I do not wish to implement out of fear that it may hamper code performance and make the code more difficult to read and understand.

        # self.logs.append("Attack Queue Unlock time: %s"%(self.attack_queue_unlock_time))
        # self.logs.append("Send Name: %s"%(self.send_name))
        # self.logs.append("Number of Sends: %s"%(self.number_of_sends))
        # self.logs.append("Max Send Amount: %s"%(self.max_send_amount))

        while self.attack_queue_unlock_time <= target_time and self.send_name != 'Zero' and (self.max_send_amount is None or self.number_of_sends < self.max_send_amount) and (self.max_eco_amount is None or self.eco < self.max_eco_amount):
            self.current_time = max(self.attack_queue_unlock_time, self.current_time)
            # self.logs.append("Advanced current time to %s"%(self.current_time))

            # First, check if we can remove any items from the attack queue
            for attack_end in self.attack_queue:
                if self.current_time >= attack_end:
                    self.attack_queue.remove(attack_end)
            
            # Next, try to add an attack to the attack_queue.
            # Can we send an attack?
            if self.cash >= self.eco_cost and len(self.attack_queue) < 6:
                # Yes, the queue is empty and we have enough cash
                if len(self.attack_queue) == 0:
                    self.attack_queue.append(self.current_time + self.eco_time)
                else:
                    self.attack_queue.append(self.attack_queue[-1] + self.eco_time)
                self.cash -= self.eco_cost
                self.eco += self.eco_gain
                self.logs.append("Sent a set of %s at time %s"%(self.send_name, self.current_time))

                # Will the attack we send fill up the queue completely?
                if len(self.attack_queue) == 5:
                    # Yes, The next send will cause the attack queue to fill up. Wait until the queue empties (if necessary)
                    self.attack_queue_unlock_time = max(self.current_time + self.eco_delay, self.attack_queue[0])
                else:
                    # No, there's still space afterwards. Check again after the eco delay is up.
                    self.attack_queue_unlock_time = self.current_time + self.eco_delay
                
                self.number_of_sends += 1

            elif len(self.attack_queue) == 6:
                # No, the queue is full!
                # NOTE: This block of code won't get reached unless the game state is initalized with a full attack queue.
                self.attack_queue_unlock_time = self.attack_queue[0]
            
            elif self.cash < self.eco_cost:
                # No, we don't have money!
                self.attack_queue_unlock_time = target_time + self.eco_delay/2

    def processBuyQueue(self, payout):
        # Helper function for advanceGameState
        
        made_purchase = False
        buy_message_list = []
        
        # DEVELOPER'S NOTE: It is possible for the queue to be empty but for there to still be purchases to be performed (via automated purchases)
        while len(self.buy_queue) > 0 and self.valid_action_flag == True:
            
            # To begin, pull out the first item in the buy queue and determine the hypothetical cash and loan amounts 
            # if this transaction was performed, as well as the minimum buy time for the transaction.

            # Also determine the hypothetical changes in revenue if the transaction was to be performed
            # Developer's Note: We must determine the hypoethetical changes in revenue beforehand rather than only when transactions are performed because of the presence of loans in the simulation.
            
            h_cash = self.cash
            h_loan = self.loan

            #For whatever reason, not putting copy.deepcopy would cause changes to h_farm_revenues to *also* apply to self.farm_revenues and so forth
            #This behavior of variable assignment is different for numbers than it is for lists.
            h_farm_revenues = copy.deepcopy(self.farm_revenues)
            h_farm_expenses = copy.deepcopy(self.farm_expenses)
            self.buffer = 0

            self.logs.append("Current value of h_farm_revenues: ")
            self.logs.append(str(h_farm_revenues))
            
            # Let's start by determining the minimum buy time.
            # NOTE: Only one object in purchase info should have minimum buy time info
            # If there are multiple values, the code will pick the latest value

            purchase_info = self.buy_queue[0]
            
            if self.min_buy_time is None:
                self.min_buy_time = 0
                # DEVELOPER NOTE: self.min_buy_time is initialized as None and set to None following the completion of a purhcase in the buy queue
                # This if condition prevents the redundant computation.
                for dict_obj in purchase_info:
                    min_buy_time = dict_obj.get('Minimum Buy Time')
                    if min_buy_time is not None:
                        if min_buy_time > self.min_buy_time:
                            self.min_buy_time = min_buy_time

                    #If the dict_obj is an IMF Loan activation, force self.min_buy_time to be at least the min_use_time of the loan
                    if dict_obj['Type'] == 'Activate IMF':
                        ind = dict_obj['Index']
                        farm = self.farms[ind]
                        if farm.min_use_time is not None and farm.min_use_time > self.min_buy_time:
                            self.min_buy_time = farm.min_use_time
                        elif farm.min_use_time is None:
                            #If the farm doesn't have a min_use_time designated, it can't be an IMF farm!
                            self.logs.append("Warning! Buy queue entry includes attempt to take out a loan from a farm that is not an IMF Loan! Aborting buy queue!")
                            self.warnings.append(len(self.logs)-1)
                            self.valid_action_flag = False
                            break
                    
                # self.logs.append("Determined the minimum buy time of the next purchase to be %s"%(self.min_buy_time))
                        
            # If we have not yet reached the minimum buy time, break the while loop. 
            # We will check this condition again later:
            if payout['Time'] < self.min_buy_time:
                break
            
            #Next, let's compute the cash and loan values we would have if the transaction was performed
            #We will also take the opportunity here to form the message that gets sent to the graph for viewCashEcoHistory
            
            for dict_obj in purchase_info:

                # DEFENSE RELATED MATTERS
                if dict_obj['Type'] == 'Buy Defense':
                    h_cash, h_loan = impact(h_cash, h_loan, -1*dict_obj['Cost'])
                    
                # FARM RELATED MATTERS
                elif dict_obj['Type'] == 'Buy Farm':
                    h_new_cash, h_new_loan = impact(h_cash, h_loan, -1*farm_globals['Farm Cost'])
                    self.farm_expenses
                elif dict_obj['Type'] == 'Upgrade Farm':
                    ind = dict_obj['Index']
                    path = dict_obj['Path']
                    farm = self.farms[ind]
                    #The following code prevents from the player from having multiple T5's in play
                    if farm.upgrades[path]+1 == 5 and self.T5_exists[path] == True:
                        self.logs.append("WARNING! Tried to purchase a T5 farm when one of the same kind already existed! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                    h_cash, h_loan = impact(h_cash, h_loan, -1*farm_upgrades_costs[path][farm.upgrades[path]])
                elif dict_obj['Type'] == 'Sell Farm':
                    ind = dict_obj['Index']
                    farm = self.farms[ind]

                    #Selling a farm counts as that farm generating revenue
                    h_new_cash, h_new_loan = impact(h_cash, h_loan, farm_sellback_values[tuple(farm.upgrades)])
                    h_farm_revenues[ind] += h_new_cash - h_cash
                    h_cash, h_loan = h_new_cash, h_new_loan

                elif dict_obj['Type'] == 'Withdraw Bank':
                    #WARNING: The farm in question must actually be a bank for us to perform a withdrawal!
                    #If it isn't, break the loop prematurely
                    ind = dict_obj['Index']
                    farm = self.farms[ind]
                    if farm.upgrades[1] < 3:
                        self.logs.append("WARNING! Tried to Withdraw from a farm that is not a bank! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                    
                    h_new_cash, h_new_loan = impact(h_cash, h_loan, farm.account_value)
                    # self.logs.append("Detected bank withdrawal of %s"%(h_new_cash - h_cash))
                    h_farm_revenues[ind] += h_new_cash - h_cash
                    h_cash, h_loan = h_new_cash, h_new_loan

                elif dict_obj['Type'] == 'Activate IMF':
                    #WARNING: The farm in question must actually be an IMF Loan for us to use this ability!
                    #If it isn't, set a flag to False and break the loop.
                    #DEVELOPER'S NOTE: A farm that has a min_use_time is not necessarily an IMF loan, it could also be an Monkeyopolis
                    if farm.upgrades[1] != 4:
                        self.logs.append("WARNING! Tried to take out a loan from a farm that is not an IMF! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                        
                    ind = dict_obj['Index']
                    farm = self.farms[ind]
                    
                    #When, a loan is activated, treat it like a payment, then add the debt
                    h_new_cash, h_new_loan = impact(h_cash, h_loan, farm_globals['IMF Loan Amount'])
                    h_farm_revenues[ind] += h_new_cash - h_cash
                    h_new_loan += farm_globals['IMF Loan Amount']
                    h_cash, h_loan = h_new_cash, h_new_loan
                
                # BOAT FARM RELATED MATTERS
                elif dict_obj['Type'] == 'Buy Boat Farm':
                    h_cash, h_loan = impact(h_cash, h_loan, -1*boat_globals['Merchantmen Cost'])
                elif dict_obj['Type'] == 'Upgrade Boat Farm':
                    ind = dict_obj['Index']
                    boat_farm = self.boat_farms[ind]
                    #The following code prevents from the player from having multiple Trade Empires in play
                    if boat_farm['Upgrade']+1 == 5 and self.Tempire_exists == True:
                        self.logs.append("WARNING! Tried to purchase a Trade Empire when one already exists! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                    upgrade_cost = boat_upgrades_costs[boat_farm['Upgrade']-3]
                    h_cash, h_loan = impact(h_cash, h_loan, -1*upgrade_cost)
                elif dict_obj['Type'] == 'Sell Boat Farm':
                    ind = dict_obj['Index']
                    boat_farm = self.boat_farms[ind]
                    h_cash, h_loan = impact(h_cash, h_loan, boat_sell_values[boat_farm['Upgrade']-3])

                # DRUID FARM RELATED MATTERS
                elif dict_obj['Type'] == 'Buy Druid Farm':
                    h_cash, h_loan = impact(h_cash, h_loan, -1*druid_globals['Druid Farm Cost'])
                elif dict_obj['Type'] == 'Sell Druid Farm':
                    if dict_obj['Index'] == self.sotf:
                        h_cash, h_loan = impact(h_cash, h_loan, game_globals['Sellback Value']*(druid_globals['Druid Farm Cost'] + druid_globals['Spirit of the Forest Upgrade Cost']))
                    else:
                        h_cash, h_loan = impact(h_cash, h_loan, game_globals['Sellback Value']*druid_globals['Druid Farm Cost'])
                elif dict_obj['Type'] == 'Buy Spirit of the Forest':
                    #WARNING: There can only be one sotf at a time!
                    if self.sotf is not None:
                        self.logs.append("WARNING! Tried to purchase a Spirit of the Forest when one already exists! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                    h_cash, h_loan = impact(h_cash, h_loan, -1*druid_globals['Spirit of the Forest Upgrade Cost'])
                
                # SUPPLY DROP RELATED MATTERS
                elif dict_obj['Type'] == 'Buy Supply Drop':
                    h_cash, h_loan = impact(h_cash, h_loan, -1*sniper_globals['Supply Drop Cost'])
                elif dict_obj['Type'] == 'Sell Supply Drop':
                    if dict_obj['Index'] == self.elite_sniper:
                        h_cash, h_loan = impact(h_cash, h_loan, game_globals['Sellback Value']*(sniper_globals['Supply Drop Cost'] + sniper_globals['Elite Sniper Upgrade Cost']) )
                    else:
                        h_cash, h_loan = impact(h_cash, h_loan, game_globals['Sellback Value']*sniper_globals['Supply Drop Cost'])
                elif dict_obj['Type'] == 'Buy Elite Sniper':
                    #WARNING: There can only be one e-sniper at a time!
                    if self.elite_sniper is not None:
                        self.logs.append("WARNING! Tried to purchase an Elite Sniper when one already exists! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                    h_cash, h_loan = impact(h_cash, h_loan, -1*sniper_globals['Elite Sniper Upgrade Cost'])

                # HELI FARM RELATED MATTERS
                elif dict_obj['Type'] == 'Buy Heli Farm':
                    h_cash, h_loan = impact(h_cash, h_loan, -1*heli_globals['Heli Farm Cost'])
                elif dict_obj['Type'] == 'Sell Heli Farm':
                    if dict_obj['Index'] == self.special_poperations:
                        h_cash, h_loan = impact(h_cash, h_loan, game_globals['Sellback Value']*(heli_globals['Heli Farm Cost'] + heli_globals['Special Poperations Upgrade Cost']) )
                    else:
                        h_cash, h_loan = impact(h_cash, h_loan, game_globals['Sellback Value']*heli_globals['Heli Farm Cost'])
                elif dict_obj['Type'] == 'Buy Special Poperations':
                    #WARNING: There can only be one Special Poperations on screen at a time!
                    if self.special_poperations is not None:
                        self.logs.append("WARNING! Tried to purchase Special Poperations when one already exists! Aborting buy queue!")
                        self.warnings.append(len(self.logs)-1)
                        self.valid_action_flag = False
                        break
                    h_cash, h_loan = impact(h_cash, h_loan, -1*heli_globals['Special Poperations Upgrade Cost'])
                    
                #If at any point while performing these operations our cash becomes negative, then prevent the transaction from occurring:
                if h_cash < 0:
                    # self.logs.append("WARNING! Reached negative cash while attempting the transaction!")
                    break

                #Read the buffer associated with the buy if any
                #NOTE: Only one object in purchase_info should have buffer info
                #If there are multiple buffers, the code rectifies the matter by
                #adding them all together
                if dict_obj.get('Buffer') is not None:
                    self.buffer += dict_obj.get('Buffer')
            
            #If the purchase sequence triggered a warning in the logs, do NOT perform it and break the while loop
            if self.valid_action_flag == False:
                break
            
            # If the amount of cash we have exceeds our buffer, perform the transaction.
            # Note at this point we have already checked whether we have reached the minimum time for the buy and also
            # we have already checked whether the buy item is valid. We now just need to check whether we have enough money!
            
            #self.logs.append("We have %s cash, but the next buy costs %s and has a buffer of %s and needs to be made on or after time %s!"%(np.round(self.cash,2), np.round(self.cash - h_cash,2),np.round(self.buffer,2), self.min_buy_time))
            if h_cash >= self.buffer:
                #If we do, perform the buy!
                made_purchase = True
                self.logs.append("We have %s cash! We can do the next buy, which costs %s and has a buffer of %s and a minimum buy time of %s!"%(np.round(self.cash,2), np.round(self.cash - h_cash,2),np.round(self.buffer,2),np.round(self.min_buy_time,2)))

                #Make the adjustments to the cash and loan amounts
                self.cash = h_cash
                self.loan = h_loan

                # Update the lists of revenues and expenses for existing farms. 
                # Note that we *might* still need to append these lists with additional entries if we bought more farms
                self.farm_revenues = h_farm_revenues
                self.farm_expenses = h_farm_expenses

                # self.logs.append("The new lists of farm revenues and expenses are given by: ")
                # self.logs.append(str(self.farm_revenues))
                # self.logs.append(str(self.farm_expenses))

                for dict_obj in purchase_info:

                    buy_message_list.append(dict_obj['Message'])
                    
                    #FARM RELATED MATTERS
                    if dict_obj['Type'] == 'Buy Farm':
                        self.logs.append("Purchasing farm!")
                        farm_info = {
                            'Purchase Time': self.current_time,
                            'Upgrades': [0,0,0]
                        }
                        farm = MonkeyFarm(farm_info)
                        
                        self.farms[self.key] = farm
                        self.key+= 1

                        #For revenue and expense tracking
                        self.farm_revenues.append(0)
                        self.farm_expenses.append(farm_globals['Farm Cost'])
                        
                    elif dict_obj['Type'] == 'Upgrade Farm':
                        ind = dict_obj['Index']
                        path = dict_obj['Path']
                        
                        self.logs.append("Upgrading path %s of the farm at index %s"%(path, ind))
                        farm = self.farms[ind]

                        #For expense tracking
                        self.farm_expenses[ind] += farm_upgrades_costs[path][farm.upgrades[path]]

                        farm.upgrades[path] += 1

                        #Update the payout information of the farm
                        farm.payout_amount = farm_payout_values[tuple(farm.upgrades)][0]
                        farm.payout_frequency = farm_payout_values[tuple(farm.upgrades)][1]
                        
                        #So that we can accurately track payments for the farm
                        farm.purchase_time = payout['Time']
                        
                        #Update the sellback value of the farm
                        farm.sell_value = farm_sellback_values[tuple(farm.upgrades)]
                        
                        self.logs.append("The new farm has upgrades (%s,%s,%s)"%(farm.upgrades[0],farm.upgrades[1],farm.upgrades[2]))
                        
                        #If the resulting farm is a Monkey Bank, indicate as such and set its max account value appropriately
                        if farm.upgrades[1] >= 3 and path == 1:
                            farm.bank = True
                            farm.max_account_value = farm_bank_capacity[farm.upgrades[1]]
                            self.logs.append("The new farm is a bank! The bank's max capacity is %s"%(farm.max_account_value))
                            
                        #If the resulting farm is an IMF Loan or Monkeyopolis, determine the earliest time the loan can be used
                        if farm.upgrades[1] > 3 and path == 1:
                            farm.min_use_time = payout['Time'] + farm_globals['Monkeynomics Initial Cooldown']
                        
                        #If the resulting farm is a Banana Central, activate the BRF buff, giving them 25% more payment amount
                        if farm.upgrades[0] == 5 and path == 0:
                            self.logs.append("The new farm is a Banana Central!")
                            self.T5_exists[0] = True
                            
                        #If the resutling farm is a Monkeyopolis, mark the x5x_exists flag as true to prevent the user from trying to have multiple of them
                        if farm.upgrades[1] == 5:
                            self.T5_exists[1] = True
                        
                        #If the resulting farm is a MWS, mark the MWS_exists flag as true to prevent the user from trying to have multiple of them.
                        if farm.upgrades[2] == 5:
                            self.T5_exists[2] = True
                        
                    elif dict_obj['Type'] == 'Sell Farm':
                        ind = dict_obj['Index']
                        farm = self.farms[ind]
                        self.logs.append("Selling the farm at index %s"%(ind))

                        # If the farm being sold is a Banana Central, we must turn off the BRF buff
                        # If the farm is a T5 of any sorts, ensure that the game state knows we no longer that particular T5

                        if farm.upgrades[0] == 5:
                            self.logs.append("The farm we're selling is a Banana Central! Removing the BRF buff.")
                            self.T5_exists[0] = False
                        elif farm.upgrades[1] == 5:
                            self.T5_exists[1] = False
                        elif farm.upgrades[2] == 5:
                            self.T5_exists[2] = False

                        #Remove the farm from the self.farms dictionary
                        self.farms.pop(ind)
                        
                    elif dict_obj['Type'] == 'Withdraw Bank':
                        self.logs.append("Withdrawing money from the bank at index %s"%(ind))
                        ind = dict_obj['Index']
                        farm = self.farms[ind]
                        farm.account_value = 0
                    elif dict_obj['Type'] == 'Activate IMF':
                        ind = dict_obj['Index']
                        farm = self.farms[ind]
                        self.logs.append("Taking out a loan from the IMF at index %s"%(ind))
                        farm.min_use_time = payout['Time'] + farm_globals['IMF Usage Cooldown']
                        
                    # BOAT FARM RELATED MATTERS
                    elif dict_obj['Type'] == 'Buy Boat Farm':
                        self.logs.append("Purchasing boat farm!")
                        boat_farm = {
                            'Purchase Time': self.current_time,
                            'Upgrade': 3
                        }
                        self.boat_farms[self.boat_key] = boat_farm
                        self.boat_key += 1
                    elif dict_obj['Type'] == 'Upgrade Boat Farm':
                        ind = dict_obj['Index']
                        
                        self.logs.append("Upgrading the boat farm at index %s"%(ind))
                        boat_farm = self.boat_farms[ind]
                        boat_farm['Upgrade'] += 1
                        
                        #Update the payout information of the boat farm
                        boat_farm['Payout'] = boat_payout_values[boat_farm['Upgrade'] - 3]
                        
                        #So that we can accurately track payments for the boat farm
                        boat['Purchase Time'] = payout['Time']
                        
                        #Update the sellback value of the boat farm
                        boat['Sell Value'] = boat_sell_values[boat_farm['Upgrade'] - 3]

                        #If the new boat farm is a Trade Empire, indicate as such
                        if boat_farm['Upgrade'] == 5:
                            self.logs.append("The new boat farm is a Trade Empire!")
                            self.Tempire_exists = True

                    elif dict_obj['Type'] == 'Sell Boat Farm':
                        ind = dict_obj['Index']
                        self.logs.append("Selling the boat farm at index %s"%(ind))
                        #If the farm being sold is a Trade Empire, indicate as such
                        if boat_farm['Upgrade'] == 5:
                            self.logs.append("The boat farm we're selling is a Trade Empire! Removing the Tempire buff.")
                            self.Tempire_exists = False
                        self.boat_farms.pop(ind)

                    # DRUID FARMS
                    elif dict_obj['Type'] == 'Buy Druid Farm':
                        self.druid_farms[self.druid_key] = payout['Time']
                        self.druid_key += 1
                        self.logs.append("Purchased a druid farm!")
                    elif dict_obj['Type'] == 'Sell Druid Farm':
                        ind = dict_obj['Index']
                        self.logs.append("Selling the druid farm at index %s"%(ind))
                        #If the druid we're selling is actually SOTF...
                        if self.sotf is not None and ind == self.sotf:
                            self.logs.append("The druid farm being sold is a Spirit of the Forest!")
                            self.sotf = None
                            self.sotf_min_use_time = None
                    elif dict_obj['Type'] == 'Buy Spirit of the Forest':
                        ind = dict_obj['Index']
                        self.sotf = ind
                        self.logs.append("Upgrading the druid farm at index %s into a Spirit of the Forest!"%(ind))
                        #Determine the minimum time that the SOTF active could be used
                        i = np.floor((20 + payout['Time'] - self.druid_farms[ind])/40) + 1
                        self.sotf_min_use_time = payout['Time'] + 20 + 40*(i-1)
                    elif dict_obj['Type'] == 'Repeatedly Buy Druid Farms':
                        self.druid_farm_max_buy_time = dict_obj['Maximum Buy Time']
                        self.druid_farm_buffer = dict_obj['Buffer']
                        self.logs.append("Triggered automated druid farm purchases until time %s"%(self.druid_farm_max_buy_time))

                    # SUPPLY DROP RELATED MATTERS
                    elif dict_obj['Type'] == 'Buy Supply Drop':
                        self.supply_drops[self.sniper_key] = payout['Time']
                        self.sniper_key += 1
                        self.logs.append("Purchased a supply drop!")
                    elif dict_obj['Type'] == 'Sell Supply Drop':
                        ind = dict_obj['Index']
                        self.logs.append("Selling the supply drop at index %s"%(ind))
                        #If the supply drop we're selling is actually an E-sniper, then...
                        if self.elite_sniper is not None:
                            if ind == self.elite_sniper:
                                self.logs.append("The supply drop being sold is an elite sniper!")
                                self.elite_sniper = None
                        
                        self.supply_drops.pop(ind)
                    elif dict_obj['Type'] == 'Buy Elite Sniper':
                        ind = dict_obj['Index']
                        self.elite_sniper = ind
                        self.logs.append("Upgrading the supply drop at index %s into an elite sniper!"%(ind))
                    elif dict_obj['Type'] == 'Repeatedly Buy Supply Drops':
                        self.supply_drop_max_buy_time = dict_obj['Maximum Buy Time']
                        self.supply_drop_buffer = dict_obj['Buffer']
                        self.logs.append("Triggered automated supply drop purchases until time %s"%(self.supply_drop_max_buy_time))

                    # HELI FARM RELATED MATTERS
                    elif dict_obj['Type'] == 'Buy Heli Farm':
                        self.heli_farms[self.heli_key] = payout['Time']
                        self.heli_key += 1
                        self.logs.append("Purchased a heli farm!")
                    elif dict_obj['Type'] == 'Sell Supply Drop':
                        ind = dict_obj['Index']
                        self.logs.append("Selling the heli farm at index %s"%(ind))
                        #If the supply drop we're selling is actually a special poperations, then...
                        if self.special_poperations is not None:
                            if ind == self.special_poperations:
                                self.logs.append("The heli farm being sold is a special poperations!")
                                self.elite_sniper = None
                        
                        self.supply_drops.pop(ind)
                    elif dict_obj['Type'] == 'Buy Special Poperations':
                        ind = dict_obj['Index']
                        self.special_poperations = ind
                        self.logs.append("Upgrading the heli farm at index %s into special poperations!"%(ind))
                    elif dict_obj['Type'] == 'Repeatedly Buy Heli Farms':
                        self.heli_farm_max_buy_time = dict_obj['Maximum Buy Time']
                        self.heli_farm_buffer = dict_obj['Buffer']
                        self.logs.append("Triggered automated heli farm purchases until time %s"%(self.heli_farm_max_buy_time))

                    # JERICHO RELATED MATTERS
                    elif dict_obj['Type'] == 'Jericho Steal':
                        self.jericho_steal_time = dict_obj['Minimum Buy Time']
                        self.jericho_steal_amount = dict_obj['Steal Amount']
                        self.cash, self.loan = impact(self.cash,self.loan, dict_obj['Steal Amount']) #If this line is not here, the sim would fail to capture the jeri payment that occurs immediately upon activation.
                        
                #Now, we have finished the for loop through purchase_info and thus correctly performed the buys
                #Remove the buy from the queue and set self.buy_cost to None so the code knows next time to re-compute
                #the buy cost for the next item in the buy queue
                self.min_buy_time = None
                self.buffer = 0
                self.buy_queue.pop(0)
                self.logs.append("Completed the buy operation! The buy queue now has %s items remaining in it"%(len(self.buy_queue)))
            else:
                #If we can't afford the buy, break the while loop
                #self.logs.append("We can't afford the buy! Terminating the buy queue while loop")
                break
        
        #...so that players can see where in the graphs their purchases are occuring
        if len(buy_message_list) > 0:
            buy_message = ', '.join(buy_message_list)
            self.buy_messages.append((payout['Time'], buy_message, 'Buy'))
        
        return made_purchase
            
# %% [markdown]
# Now it's time to define the MonkeyFarm class!

# %%
class MonkeyFarm():
    def __init__(self, initial_state):
        
        ###############
        #BASIC FEATURES
        ###############
        
        #self.upgrades is an array [i,j,k] representing the upgrade state of the farm
        #EXAMPLE: [4,2,0] represents a Banana Research Facility with Valuable Bananas
        
        self.upgrades = initial_state.get('Upgrades')
        self.sell_value = farm_sellback_values[tuple(self.upgrades)]
        
        self.purchase_time = initial_state.get('Purchase Time')
        
        self.payout_amount = farm_payout_values[tuple(self.upgrades)][0]
        self.payout_frequency = farm_payout_values[tuple(self.upgrades)][1]
        
        ##############
        #BANK FEATURES
        ##############
        
        self.bank = False

        #If the farm is a bank, mark is as such
        if self.upgrades[1] >= 3:
            self.bank = True
        
        self.account_value = 0
        self.max_account_value = farm_bank_capacity[self.upgrades[1]]
        
        #Regarding the IMF Loan/Monkeyopolis active ability
        self.min_use_time = None
        if self.upgrades[1] >= 4:
            self.min_use_time = self.purchase_time + farm_globals['Monkeynomics Initial Cooldown']



# %% [markdown]
# The goal of a simulator like this is to compare different strategies and see which one is better. To this end, we define a function capable of simulating multiple game states at once and comparing them.

# %%
def compareStrategies(initial_state, eco_queues, buy_queues, target_time = None, target_round = 30, display_farms = True):
    
    # Log file in case we need to check outputs
    logs = []
    
    # Given an common initial state and N different tuples of (eco_queue, buy_queue), 
    # Build N different instances of GameState, advance them to the target_time (or target round if specified)
    # Finally, graph their cash and eco histories
    
    # To begin, let's form the GameState objects we will use in our analysis!
    game_states = []
    farm_incomes = []
    N = len(eco_queues)
    for i in range(N):
        init = initial_state
        init['Eco Queue'] = eco_queues[i]
        init['Buy Queue'] = buy_queues[i]
        #print(init['Supply Drops'])
        game_states.append(GameState(init))
    
    #########################
    # GRAPH CASH & ECO STATES
    #########################
    
    #Now intialize the graphs, one for cash and one for eco
    fig, ax = plt.subplots(2)
    fig.set_size_inches(8,12)
    
    #For each GameState object, advance the time, and then graph the cash and eco history
    i = 0
    cash_min = None
    if target_round is not None:
        #Use the target round instead of the target time if specified
        target_time = game_states[0].rounds.getTimeFromRound(target_round)

    for game_state in game_states:
        logs.append("Simulating Game State %s"%(i))
        game_state.fastForward(target_time = target_time)
        
        ax[0].plot(game_state.time_states, game_state.cash_states, label = "Cash of Game State %s"%(i))
        ax[1].plot(game_state.time_states, game_state.eco_states, label = "Eco of Game State %s"%(i))
        
        farm_income = 0
        for key in game_state.farms.keys():
            #WARNING: This is not a great measure to go by if the player has farms
            farm = game_state.farms[key]
            if game_state.T5_exists[0] == True and farm.upgrades[0] == 4:
                #If the farm is a BRF being buffed by Banana Central
                farm_income += 1.25*farm.payout_amount*farm.payout_frequency
            elif farm.upgrades[2] == 5:
                #If the farm is a Monkey Wall Street
                farm_income += 10000 + farm.payout_amount*farm.payout_frequency
            elif farm.upgrades[1] >= 3:
                #This is an *estimate* based on the impact of one round of bank payments
                farm_income = farm_income + 1.2*(farm.payout_amount*farm.payout_frequency + 400)
            else:
                farm_income += farm.payout_amount*farm.payout_frequency
        farm_incomes.append(farm_income)
            
        
        if cash_min is None:
            cash_min = min(game_state.cash_states)
            eco_min = min(game_state.eco_states)
            
            cash_max = max(game_state.cash_states)
            eco_max = max(game_state.eco_states)
            
        else:
            candidate_cash_min = min(game_state.cash_states)
            candidate_eco_min = min(game_state.eco_states)
            
            if candidate_cash_min < cash_min:
                cash_min = candidate_cash_min
            if candidate_eco_min < eco_min:
                eco_min = candidate_eco_min
            
            candidate_cash_max = max(game_state.cash_states)
            candidate_eco_max = max(game_state.eco_states)
            
            if candidate_cash_max > cash_max:
                cash_max = candidate_cash_max
            if candidate_eco_max > eco_max:
                eco_max = candidate_eco_max
        
        i += 1

    ####################
    # GRAPH ROUND STARTS
    ####################
    
    # Also, graph when the rounds start
    # DEVELOPER'S NOTE: We are dealing with multiple game states where the stall factor in each game state may change
    # For now, I will just take the round starts from game state 0, but I'll have to adjust this later on down the road.
    
    round_to_graph = initial_state['Rounds'].getRoundFromTime(game_states[0].time_states[0]) + 1
    while initial_state['Rounds'].round_starts[round_to_graph] <= game_states[0].time_states[-1]:
        logs.append("Graphing round %s, which starts at time %s"%(str(round_to_graph),str(initial_state['Rounds'].round_starts[round_to_graph])))
        ax[0].plot([initial_state['Rounds'].round_starts[round_to_graph], initial_state['Rounds'].round_starts[round_to_graph]],[cash_min, cash_max], label = "R" + str(round_to_graph) + " start")
        ax[1].plot([initial_state['Rounds'].round_starts[round_to_graph], initial_state['Rounds'].round_starts[round_to_graph]],[eco_min, eco_max], label = "R" + str(round_to_graph) + " start")
        round_to_graph += 1

    #################
    # DISPLAY VISUALS
    #################
    
    ax[0].set_title("Cash vs Time")
    ax[1].set_title("Eco vs Time")

    ax[0].set_ylabel("Cash")
    ax[1].set_ylabel("Eco")

    ax[1].set_xlabel("Time (seconds)")

    ax[0].legend(loc='upper left')
    ax[1].legend(loc='upper left')
    
    d = {'Game State': [i for i in range(N)], 'Farm Income': [farm_incomes[i] for i in range(N)]}
    df = pd.DataFrame(data=d)
    
    fig.tight_layout()
    display(df)
    logs.append("Successfully generated graph! \n")

# def equivalentEcoImpact(time_tuple, rounds, farms = None, boat_farms = None, druid_farms = None, supply_drops = None, time_type = 'Rounds'):
#     #Given some collection of farms and a span of time, determine the amount of the eco that would make the same amount of money as those farms in that time span
#     assert type(time_tuple) == tuple and len(time_tuple) == 2, "ERROR! time_tuple must be of the form (start, end)"

#     #We expect in most cases that the player will indicate start and end rounds for this function. In that case, convert the starting round and ending rounds to times
#     if time_type == 'Rounds':
#         start_time = rounds.getTimeFromRound(time_tuple[0])
#         end_time = rounds.getTimeFromRound(time_tuple[1])

#     #If the farms contain any banks, we will add actions to the buy queue to withdraw from these banks upon reaching the target time
#     buy_queue = []

#     for farm_info_entry in farms:
#         if farms[key]['Upgrades'][1] >= 3:
#             buy_queue.append([withdrawBank(key, min_buy_time = end_time)])

#     initial_state_game = {
#         'Cash': 0,
#         'Eco': 0,
#         'Rounds': rounds,
#         'Game Time': start_time,
#         'Farms': farms,
#         'Boat Farms': boat_farms,
#         'Druid Farms': druid_farms,
#         'Supply Drops': supply_drops
#     }

#     game_state = GameState(initial_state_game)
#     game_state.fastForward(target_time = end_time)

#     #Now compute the formula for equivlaent eco impact
#     return 6*game_state.cash/(end_time - start_time)

# %%
