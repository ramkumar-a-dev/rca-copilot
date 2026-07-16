from rca_copilot.incidents import random_incident

incident = random_incident()

print(f"ROOT CAUSE: {incident.root_cause}\n")
print(f"NARRATIVE: {incident.narrative}\n")
print("EVENTS (what the agent will see):")
for event in incident.events:
    print(f"  {event.render()}")