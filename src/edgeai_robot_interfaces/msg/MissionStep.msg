# High-level mission semantics only. Robot assignment is deliberately absent;
# it belongs to the multi-robot coordinator, not the LLM.
string step_id
string target_id

uint8 ACTION_RESCUE=1
uint8 action_type

# 数值越大优先级越高；0表示指令未表达优先级。优先级只在多个步骤同时可执行时
# 影响调度顺序，不能替代predecessor_step_ids表达的先后约束。
uint32 priority
string[] predecessor_step_ids
