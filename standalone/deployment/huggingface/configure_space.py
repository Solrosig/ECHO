"""Switch ECHO's conversation model between the two Hugging Face variants. Dry run unless --apply.

  a    One Space: the ECHO Space runs Ollama itself on paid GPU hardware and sleeps after --sleep seconds.
  b    Split: the ECHO Space stays on free ZeroGPU; a private Docker Space runs Ollama on paid hardware, sleeps
       after --sleep seconds and is woken by the website when someone opens Explore.
  off  Back to ZeroGPU without conversation replies; the conversation Space, if it exists, is paused.

Uses this computer's Hugging Face login (hf auth login). Variant b also needs ECHO_OLLAMA_TOKEN in the environment:
a fine-grained token that can only read the conversation Space. It is stored as a Space secret and never printed.
Paid hardware is billed per minute while a Space is starting or awake, never while it sleeps or is paused.
The ECHO Space must already run code that understands ECHO_LLM_MODE (package_space.py builds it).
"""
import argparse
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LLM_FOLDER = HERE.parent / 'huggingface-llm'
ZERO_GPU = 'zero-a10g'


def plan_for(args):
    sleep = args.sleep or (3600 if args.variant == 'a' else 900)
    host = 'https://' + args.llm_space.replace('/', '-').replace('_', '-').replace('.', '-').lower() + '.hf.space'
    if args.variant == 'a':
        return [('set variable', args.space, 'ECHO_LLM_MODE', 'embedded'), ('remove variable', args.space, 'ECHO_OLLAMA_URL'),
                ('remove secret', args.space, 'ECHO_OLLAMA_TOKEN'), ('set hardware', args.space, args.hardware, sleep),
                ('pause if it exists', args.llm_space)]
    if args.variant == 'b':
        return [('create private Docker Space', args.llm_space, args.hardware, sleep), ('upload folder', args.llm_space, str(LLM_FOLDER)),
                ('set variable', args.space, 'ECHO_LLM_MODE', 'remote'), ('set variable', args.space, 'ECHO_OLLAMA_URL', host),
                ('set secret', args.space, 'ECHO_OLLAMA_TOKEN', '(value of ECHO_OLLAMA_TOKEN)'), ('set hardware', args.space, ZERO_GPU, None)]
    return [('set variable', args.space, 'ECHO_LLM_MODE', 'off'), ('set hardware', args.space, ZERO_GPU, None),
            ('pause if it exists', args.llm_space)]


def apply(steps):
    from huggingface_hub import HfApi
    api = HfApi()
    for step in steps:
        action, repo = step[0], step[1]
        if action == 'set variable':
            api.add_space_variable(repo, step[2], step[3])
        elif action == 'remove variable':
            if step[2] in api.get_space_variables(repo):
                api.delete_space_variable(repo, step[2])
        elif action == 'remove secret':
            if step[2] in api.get_space_secrets(repo):
                api.delete_space_secret(repo, step[2])
        elif action == 'set secret':
            api.add_space_secret(repo, step[2], os.environ['ECHO_OLLAMA_TOKEN'])
        elif action == 'set hardware':
            runtime = api.get_space_runtime(repo)
            if step[3] is None and step[2] in (runtime.hardware, runtime.requested_hardware):
                print('unchanged:', action, repo, step[2], flush=True)
                continue
            api.request_space_hardware(repo, step[2], sleep_time=step[3])
        elif action == 'create private Docker Space':
            # A Space created in the web interface is reused, so the login token needs no right to create repositories.
            if not api.repo_exists(repo, repo_type='space'):
                api.create_repo(repo, repo_type='space', space_sdk='docker', private=True)
            api.request_space_hardware(repo, step[2], sleep_time=step[3])
        elif action == 'upload folder':
            api.upload_folder(repo_id=repo, repo_type='space', folder_path=step[2])
        elif action == 'pause if it exists':
            if not api.repo_exists(repo, repo_type='space'):
                continue
            api.pause_space(repo)
        print('done:', action, repo, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('variant', choices=['a', 'b', 'off'])
    parser.add_argument('--space', default='solrosig/echo-tts', help='the public ECHO Space')
    parser.add_argument('--llm-space', default='solrosig/echo-llm', help='variant b: the private conversation Space')
    parser.add_argument('--hardware', default='t4-small',
                        help='variant a: the ECHO Space; variant b: the conversation Space (cpu-upgrade is cheaper and slower)')
    parser.add_argument('--sleep', type=int, help='seconds without requests before sleeping (default: a 3600, b 900)')
    parser.add_argument('--apply', action='store_true', help='make the changes; without it the plan is only printed')
    args = parser.parse_args()
    steps = plan_for(args)
    for step in steps:
        print(('APPLY  ' if args.apply else 'PLAN   ') + ' | '.join('' if part is None else str(part) for part in step))
    if not args.apply:
        print('Dry run: nothing changed. Re-run with --apply to make these changes.')
        return
    if args.variant == 'b' and not os.environ.get('ECHO_OLLAMA_TOKEN', '').startswith('hf_'):
        raise SystemExit('Set ECHO_OLLAMA_TOKEN to a read token for the conversation Space before --apply.')
    apply(steps)


if __name__ == '__main__':
    main()
