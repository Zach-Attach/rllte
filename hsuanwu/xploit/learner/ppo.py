import torch
from torch import nn

from hsuanwu.common.typing import Space, Tensor, Dict, Device, Storage
from hsuanwu.xploit.learner.base import BaseLearner
from hsuanwu.xploit.learner.network import DiscreteActorCritic


class PPOLearner(BaseLearner):
    """Proximal Policy Optimization (PPO) Learner.

    Args:
        observation_space (Space): Observation space of the environment.
        action_space (Space): Action shape of the environment.
        action_type (str): Continuous or discrete action. "cont" or "dis".
        device (Device): Device (cpu, cuda, ...) on which the code should be run.
        feature_dim (int): Number of features extracted.
        lr (float): The learning rate.
        eps (float): Term added to the denominator to improve numerical stability.

        hidden_dim (int): The size of the hidden layers.
        clip_range (float): Clipping parameter.
        n_epochs (int): Times of updating the policy.
        num_mini_batch (int): Number of mini-batches.
        vf_coef (float): Weighting coefficient of value loss.
        ent_coef (float): Weighting coefficient of entropy bonus.
        max_grad_norm (float): Maximum norm of gradients.

    Returns:
        PPO learner instance.
    """

    def __init__(
        self,
        observation_space: Space,
        action_space: Space,
        action_type: str,
        device: Device = 'cuda',
        feature_dim: int = 256,
        lr: float = 5e-4,
        eps: float = 1e-5,
        hidden_dim: int = 256,
        clip_range: float = 0.2,
        n_epochs: int = 3,
        num_mini_batch: int = 8,
        vf_coef: float = 0.5,
        ent_coef: float = 0.01,
        max_grad_norm: float = 0.5,
    ) -> None:
        super().__init__(
            observation_space, action_space, action_type, device, feature_dim, lr, eps
        )

        self.n_epochs = n_epochs
        self.clip_range = clip_range
        self.num_mini_batch = num_mini_batch
        self.vf_coef = vf_coef
        self.ent_coef = ent_coef
        self.max_grad_norm = max_grad_norm

        # create models
        if self.action_type == 'dis':
            self.ac = DiscreteActorCritic(
                action_space=action_space, feature_dim=feature_dim, hidden_dim=hidden_dim
            ).to(self.device)
        else:
            raise NotImplementedError

        # create optimizers
        self.ac_opt = torch.optim.Adam(self.ac.parameters(), lr=lr, eps=eps)
        self.train()

    def train(self, training: bool = True) -> None:
        """Set the train mode.

        Args:
            training (bool): True (training) or False (testing).

        Returns:
            None.
        """
        self.training = training
        self.ac.train(training)
        if self.encoder is not None:
            self.encoder.train(training)

    def get_value(self, obs: Tensor) -> Tensor:
        """Get estimated values for observations.

        Args:
            obs (Tensor): Observations.

        Returns:
            Estimated values.
        """
        encoded_obs = self.encoder(obs)
        return self.ac.get_value(obs=encoded_obs)

    def update(self, rollout_storage: Storage, episode: int = 0) -> Dict[str, float]:
        """Update the learner.

        Args:
            rollout_storage (Storage): Hsuanwu rollout storage.
            episode (int): Global training episode.

        Returns:
            Training metrics such as actor loss, critic_loss, etc.
        """
        total_actor_loss = 0.0
        total_critic_loss = 0.0
        total_entropy_loss = 0.0

        for e in range(self.n_epochs):
            generator = rollout_storage.generator(self.num_mini_batch)

            for batch in generator:
                (
                    batch_obs,
                    batch_actions,
                    batch_values,
                    batch_returns,
                    batch_terminateds,
                    batch_truncateds,
                    batch_old_log_probs,
                    adv_targ,
                ) = batch

                # evaluate sampled actions
                _, values, log_probs, entropy = self.ac.get_action_and_value(
                    obs=self.encoder(batch_obs), actions=batch_actions
                )

                # actor loss part
                ratio = torch.exp(log_probs - batch_old_log_probs)
                surr1 = ratio * adv_targ
                surr2 = (
                    torch.clamp(ratio, 1.0 - self.clip_range, 1.0 + self.clip_range)
                    * adv_targ
                )
                actor_loss = -torch.min(surr1, surr2).mean()

                # critic loss part
                values_clipped = batch_values + (values - batch_values).clamp(
                    -self.clip_range, self.clip_range
                )
                values_losses = (batch_values - batch_returns).pow(2)
                values_losses_clipped = (values_clipped - batch_returns).pow(2)
                critic_loss = (
                    0.5 * torch.max(values_losses, values_losses_clipped).mean()
                )

                # update
                self.encoder_opt.zero_grad(set_to_none=True)
                self.ac_opt.zero_grad(set_to_none=True)
                (
                    critic_loss * self.vf_coef + actor_loss - entropy * self.ent_coef
                ).backward()
                nn.utils.clip_grad_norm_(
                    self.encoder.parameters(), self.max_grad_norm
                )
                nn.utils.clip_grad_norm_(self.ac.parameters(), self.max_grad_norm)
                self.ac_opt.step()
                self.encoder_opt.step()

                total_actor_loss += actor_loss.item()
                total_critic_loss += critic_loss.item()
                total_entropy_loss += entropy.item()

        num_updates = self.n_epochs * self.num_mini_batch

        total_actor_loss /= num_updates
        total_critic_loss /= num_updates
        total_entropy_loss /= num_updates

        return {
            "actor_loss": total_actor_loss,
            "critic_loss": total_critic_loss,
            "entropy": total_entropy_loss,
        }
