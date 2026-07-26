from voice_manager import VoiceManager


manager = VoiceManager()

print("Available voices:")

for voice in manager.list_voices():
    print("-", voice)


print("\nDefault voice:")
print(manager.get_voice_path())

