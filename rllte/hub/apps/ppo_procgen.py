from rllte.xploit.agent import PPO
from rllte.xploit.encoder import EspeholtResidualEncoder
from rllte.env import make_procgen_env
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--env-id", type=str, default="bigfish")
parser.add_argument("--device", type=str, default="cuda")
parser.add_argument("--seed", type=int, default=1)

if __name__ == "__main__":
    args = parser.parse_args()
    # create env
    env = make_procgen_env(
        env_id=args.env_id,
        num_envs=64,
        device=args.device,
        seed=args.seed,
        gamma=0.99,
        num_levels=200,
        start_level=0,
        distribution_mode="easy"
    )
    eval_env = make_procgen_env(
        env_id=args.env_id,
        num_envs=1,
        device=args.device,
        seed=args.seed,
        gamma=0.99,
        num_levels=0,
        start_level=0,
        distribution_mode="easy"
    )
    # create agent
    feature_dim = 256
    agent = PPO(
        env=env,
        eval_env=eval_env,
        tag=f"ppo_procgen_{args.env_id}_seed_{args.seed}",
        seed=args.seed,
        device=args.device,
        num_steps=256,
        feature_dim=feature_dim,
        batch_size=2048,
        lr=5e-4,
        eps=1e-5,
        clip_range=0.2,
        clip_range_vf=0.2,
        n_epochs=3,
        vf_coef=0.5,
        ent_coef=0.01,
        max_grad_norm=0.5,
        network_init_method="xavier_uniform"
    )
    encoder = EspeholtResidualEncoder(
        observation_space=env.observation_space,
        feature_dim=feature_dim
    )
    agent.set(encoder=encoder)
    # training
    agent.train(num_train_steps=25000000)