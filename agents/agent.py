import numpy as np
# import tensorflow as tf

from atari import Atari
from agents.exploration_bonus import ExplorationBonus


class Agent(object):
  def __init__(self, policy_network, replay_memory, summary, config):
    self.config = config
    self.policy_network = policy_network
    self.replay_memory = replay_memory
    self.summary = summary

    # Create environment
    self.atari = Atari(summary, config)
    self.exploration_bonus = ExplorationBonus(config)

  def new_game(self):
    self.policy_network.sample_head()
    observation, reward, done = self.atari.reset()
    self.replay_memory.store_new_episode(observation)
    return observation, reward, done

  def action(self, session, step, observation):
    # Epsilon greedy exploration/exploitation even for bootstrapped DQN
    if self.config.LLL:
      [e_vals, vals] = session.run(
          [self.policy_network.action_values, self.policy_network.action_e_values],
          {self.policy_network.inputs.observations: [observation],
           self.policy_network.inputs.alive: np.reshape([1],(1,1))})
      return np.argmax(vals - self.epsilon(step) * np.log(-np.log(e_vals)))

    elif np.random.rand() < self.epsilon(step):
      return self.atari.sample_action()
    else:
      [action] = session.run(
          self.policy_network.choose_action,
          {self.policy_network.inputs.observations: [observation]})
      return action

  def epsilon(self, step):
    """Epsilon is linearly annealed from an initial exploration value
    to a final exploration value over a number of steps"""

    initial = self.config.initial_exploration
    final = self.config.final_exploration
    final_frame = self.config.final_exploration_frame

    annealing_rate = (initial - final) / final_frame
    annealed_exploration = initial - (step * annealing_rate)
    epsilon = max(annealed_exploration, final)

    self.summary.epsilon(step, epsilon)

    return epsilon

  def take_action(self, action, last_observation=None, session=None):


    observation, reward, done = self.atari.step(action)

    if self.config.e_exploration_bonus:
      if session is None:
        e_value = 0.5

      elif self.config.actor_critic:
        [e_value] = session.run(
            self.policy_network.evalue,
            {self.policy_network.inputs.observations: [observation],
             self.policy_network.inputs.alive: np.reshape([1],(1,1))})
        e_value = e_value*-1

      else:
        [e_value] = session.run(
            self.policy_network.taken_action_e_value,
            {self.policy_network.inputs.observations: [last_observation],
             self.policy_network.inputs.action: np.reshape([action],(1,1)),
             self.policy_network.inputs.alive: np.reshape([1],(1,1))})
    else:
      e_value = 0

    training_reward = self.process_reward(reward, observation, e_value)

    # Store action, reward and done with the next observation
    self.replay_memory.store_transition(action, training_reward, done,
                                        observation)

    return observation, reward, done

  def process_reward(self, reward, frames, e_value):
    if self.config.exploration_bonus:
      reward += self.exploration_bonus.bonus(frames)

    if self.config.e_exploration_bonus:
        counter = -np.log(e_value)
        exploration_bonus = self.config.exploration_beta / ((counter + 0.01)**0.5)
        reward += exploration_bonus

    if self.config.reward_clipping:
      reward = max(-self.config.reward_clipping,
                   min(reward, self.config.reward_clipping))

    return reward

  def populate_replay_memory(self):
    """Play game with random actions to populate the replay memory"""

    count = 0
    done = True

    while count < self.config.replay_start_size or not done:
      if done: self.new_game()
      _, _, done = self.take_action(self.atari.sample_action())
      count += 1

    self.atari.episode = 0

  def log_episode(self, step):
    self.atari.log_episode(step)
