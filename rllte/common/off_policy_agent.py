# =============================================================================
# MIT License

# Copyright (c) 2023 Reinforcement Learning Evolution Foundation

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# =============================================================================


from collections import deque
from pathlib import Path
from typing import Dict, Optional

import gymnasium as gym
import numpy as np
import torch as th

from rllte.common import utils
from rllte.common.base_agent import BaseAgent


class OffPolicyAgent(BaseAgent):
    """Trainer for off-policy algorithms.

    Args:
        env (gym.Env): A Gym-like environment for training.
        eval_env (gym.Env): A Gym-like environment for evaluation.
        tag (str): An experiment tag.
        seed (int): Random seed for reproduction.
        device (str): Device (cpu, cuda, ...) on which the code should be run.
        pretraining (bool): Turn on pre-training model or not.
        num_init_steps (int): Number of initial exploration steps.
        **kwargs: Arbitrary arguments such as `batch_size` and `hidden_dim`.

    Returns:
        Off-policy agent instance.
    """

    def __init__(
        self,
        env: gym.Env,
        eval_env: Optional[gym.Env] = None,
        tag: str = "default",
        seed: int = 1,
        device: str = "cpu",
        pretraining: bool = False,
        num_init_steps: int = 2000,
        **kwargs,
    ) -> None:
        super().__init__(env=env, eval_env=eval_env, tag=tag, seed=seed, device=device, pretraining=pretraining)

        self.num_init_steps = num_init_steps

    def update(self) -> Dict[str, float]:
        """Update the agent. Implemented by individual algorithms."""
        raise NotImplementedError

    def train(
        self,
        num_train_steps: int,
        init_model_path: Optional[str] = None,
        log_interval: int = 1,
        eval_interval: int = 5000,
        num_eval_episodes: int = 10,
    ) -> None:
        """Training function.

        Args:
            num_train_steps (int): The number of training steps.
            init_model_path (Optional[str]): The path of the initial model.
            log_interval (int): The interval of logging.
            eval_interval (int): The interval of evaluation.
            num_eval_episodes (int): The number of evaluation episodes.

        Returns:
            None.
        """
        # freeze the agent and get ready for training
        self.freeze(init_model_path=init_model_path)

        # reset the env
        episode_rewards = deque(maxlen=10)
        episode_steps = deque(maxlen=10)
        obs, infos = self.env.reset(seed=self.seed)

        # training loop
        while self.global_step <= num_train_steps:
            # try to eval
            if (self.global_step % eval_interval) == 0 and (self.eval_env is not None):
                eval_metrics = self.eval(num_eval_episodes)

                # log to console
                self.logger.eval(msg=eval_metrics)

            # sample actions
            with th.no_grad(), utils.eval_mode(self):
                # Initial exploration
                if self.global_step <= self.num_init_steps:
                    actions = self.policy.explore(obs)
                else:
                    actions = self.policy(obs, training=True, step=self.global_step)

            # observe reward and next obs
            next_obs, rews, terms, truncs, infos = self.env.step(actions)
            self.global_step += self.num_envs

            # pre-training mode
            if self.pretraining:
                rews = th.zeros_like(rews, device=self.device)

            # add new transitions
            self.storage.add(obs, actions, rews, terms, truncs, infos, next_obs)

            # update agent
            if self.global_step >= self.num_init_steps:
                metrics = self.update()
                # try to update storage
                self.storage.update(metrics)

            # get episode information
            if "episode" in infos:
                eps_r, eps_l = utils.get_episode_statistics(infos)
                episode_rewards.extend(eps_r)
                episode_steps.extend(eps_l)
                self.global_episode += len(eps_r)

            # log training information
            if len(episode_rewards) > 1 and (self.global_step % log_interval) == 0:
                total_time = self.timer.total_time()

                # log to console
                train_metrics = {
                    "step": self.global_step,
                    "episode": self.global_episode,
                    "episode_length": np.mean(episode_steps),
                    "episode_reward": np.mean(episode_rewards),
                    "fps": self.global_step / total_time,
                    "total_time": total_time,
                }
                self.logger.train(msg=train_metrics)

                # As the vector environments autoreset for a terminating and truncating sub-environments,
                # the returned observation and info is not the final step's observation or info which
                # is instead stored in info as `final_observation` and `final_info`. Therefore,
                # we don't need to reset the env here.

            # set the current observation
            obs = next_obs

        # save model
        self.logger.info("Training Accomplished!")
        if self.pretraining:  # pretraining
            save_dir = Path.cwd() / "pretrained"
            save_dir.mkdir(exist_ok=True)
        else:
            save_dir = Path.cwd() / "model"
            save_dir.mkdir(exist_ok=True)
        self.policy.save(path=save_dir, pretraining=self.pretraining)
        self.logger.info(f"Model saved at: {save_dir}")

        # close env
        self.env.close()
        if self.eval_env is not None:
            self.eval_env.close()

    def eval(self, num_eval_episodes: int) -> Dict[str, float]:
        """Evaluation function.

        Args:
            num_eval_episodes (int): The number of evaluation episodes.

        Returns:
            The evaluation results.
        """
        # reset the env
        obs, infos = self.eval_env.reset(seed=self.seed)
        episode_rewards = list()
        episode_steps = list()

        # evaluation loop
        while len(episode_rewards) < num_eval_episodes:
            # sample actions
            with th.no_grad(), utils.eval_mode(self):
                actions = self.policy(obs, training=False, step=self.global_step)

            # observe reward and next obs
            next_obs, rews, terms, truncs, infos = self.eval_env.step(actions)

            # get episode information
            if "episode" in infos:
                eps_r, eps_l = utils.get_episode_statistics(infos)
                episode_rewards.extend(eps_r)
                episode_steps.extend(eps_l)

            # set the current observation
            obs = next_obs

        return {
            "step": self.global_step,
            "episode": self.global_episode,
            "episode_length": np.mean(episode_steps),
            "episode_reward": np.mean(episode_rewards),
            "total_time": self.timer.total_time(),
        }
