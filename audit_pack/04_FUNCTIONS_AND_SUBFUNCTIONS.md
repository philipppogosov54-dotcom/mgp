# Functions and Subfunctions

## Node Handlers (app/agent/nodes.py)

| Function | Line | Input | Output | Side Effects | Error Handling |
|----------|------|-------|--------|--------------|----------------|
| `input_analyzer` | 2754 | AgentState | AgentState | Updates search_params, intent, cascade_stage | try/except → state["error"] |
| `tour_searcher` | 3901 | AgentState | AgentState | API call, updates tour_offers | try/except → fallback message |
| `faq_handler` | 3663 | AgentState | AgentState | Sets response from FAQ_RESPONSES | None |
| `booking_handler` | 5407 | AgentState | AgentState | Sets awaiting_phone, is_group_request | None |
| `quality_check_handler` | 3833 | AgentState | AgentState | Sets quality_check_asked, response | None |
| `responder` | 4852 | AgentState | AgentState | Formats final response with tour cards | None |
| `general_chat_handler` | 3774 | AgentState | AgentState | Generic response | None |
| `invalid_country_handler` | 3720 | AgentState | AgentState | Suggests alternatives | None |
| `child_ages_handler` | 3740 | AgentState | AgentState | Asks for child ages | None |
| `clarify_city_handler` | 5626 | AgentState | AgentState | Asks city clarification | None |
| `more_tours_handler` | 5553 | AgentState | AgentState | Pagination | None |
| `continue_search_handler` | 5486 | AgentState | AgentState | Deeper search | None |

## Entity Extraction (app/agent/nodes.py)

| Function | Line | Input | Output | Description |
|----------|------|-------|--------|-------------|
| `extract_entities_regex` | 1169 | text, last_question_type, today_override | dict | Main regex-based entity extraction |
| `extract_entities_with_llm` | 2505 | text, awaiting_phone, last_question_type | dict | LLM-based extraction (YandexGPT) |
| `detect_intent_regex` | 2448 | text, awaiting_phone | str | Intent detection (search_tour, faq, booking, etc.) |
| `detect_search_mode` | 784 | text | str | "package" / "hotel_only" / "burning" |
| `detect_phone_number` | 2435 | text | Optional[str] | Phone number extraction |
| `check_agreement_phrase` | 2743 | text | bool | User agreement detection |

## Routing (app/agent/nodes.py)

| Function | Line | Input | Output | Description |
|----------|------|-------|--------|-------------|
| `should_search` | 5669 | AgentState | str | Conditional edge routing |

## Response Formatting (app/agent/nodes.py)

| Function | Line | Input | Output | Description |
|----------|------|-------|--------|-------------|
| `clean_response_text` | 903 | text, is_first_message | str | Remove duplicate greetings |
| `generate_fallback_response` | 3808 | user_message, params | str | Fallback when no intent |
| `generate_no_results_explanation` | 4728 | params, state | tuple[str, bool, str] | Explain no tours found |

## Tourvisor Service (app/services/tourvisor.py)

| Function | Line | Input | Output | Side Effects | Error Handling |
|----------|------|-------|--------|--------------|----------------|
| `search_tours` | ~800 | SearchRequest | SearchResponse | HTTP to Tourvisor | try/except → empty list |
| `get_hot_tours` | ~1200 | country_id, departure_id | list[TourOffer] | HTTP to Tourvisor | try/except → empty list |
| `get_hotel_content` | ~1500 | hotel_id | HotelDetails | HTTP to Tourvisor | try/except → None |
| `get_countries` | ~200 | None | dict | HTTP to Tourvisor | Cache on success |
| `get_departures` | ~300 | None | dict | HTTP to Tourvisor | Cache on success |
| `get_regions` | ~400 | country_id | list[dict] | HTTP to Tourvisor | Cache on success |

## State Management (app/agent/state.py)

| Function | Line | Input | Output | Description |
|----------|------|-------|--------|-------------|
| `create_initial_state` | 474 | None | AgentState | Create empty state |
| `get_cascade_stage` | 244 | params, search_mode | int | Current cascade stage (1-6) |
| `get_missing_required_params` | 331 | params, search_mode | list[str] | Missing required slots |
| `needs_quality_check` | 379 | params | bool | Should ask stars/food |
| `check_skip_quality_phrase` | 396 | text | bool | "любой"/"не важно" detection |
| `format_context` | 419 | params | str | Format collected params for display |

## Session Management (app/core/session.py)

| Function | Description |
|----------|-------------|
| `session_manager.get_config(thread_id)` | Get LangGraph config for thread |
| `session_manager.get_checkpointer()` | Get MemorySaver or AsyncPostgresSaver |
| `session_manager.increment_message_count(thread_id)` | Update session metadata |
| `apply_window_buffer(messages, max)` | Trim to last N messages |

## Guardrails (app/core/guardrails.py)

| Function | Description |
|----------|-------------|
| `apply_input_guardrails(text)` | Sanitize user input, detect injection |
| `apply_output_guardrails(text, error=None)` | Sanitize bot output, hide errors |

## Graph (app/agent/graph.py)

| Function | Line | Description |
|----------|------|-------------|
| `create_agent_graph` | 60 | Build StateGraph with all nodes |
| `get_agent_graph` | 161 | Get or create singleton graph |
| `reinitialize_graph` | 170 | Recreate graph (after async init) |
| `process_message` | 181 | Main entry point for message processing |
