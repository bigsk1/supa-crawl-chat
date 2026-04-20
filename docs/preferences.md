# User Preference System

## Overview

The User Preference System is a sophisticated component of the Supa Crawl Chat application that enables the AI to remember and utilize information about users across conversations. This document explains how preferences are extracted, stored, retrieved, and utilized throughout the application.

## Current Behavior

This app is optimized for a local single-user setup. The browser keeps a local user profile in `localStorage`, and the backend exposes `GET /api/chat/defaults` so the UI can initialize that profile from `CHAT_USER_ID` without duplicating the setting in frontend env. If `CHAT_USER_ID=bigsk1` and the browser profile is still the generic `User`, the UI will switch to `bigsk1` automatically after startup/login.

Conversation history and preferences are separate:

- `chat_conversations` is scoped by `session_id` and preserves turns for a specific chat session.
- `user_preferences` is scoped by `user_id` and acts as long-term memory across sessions.
- Chat injects only active preferences for the current `user_id`.
- Chat now ranks memories for the current question instead of blindly injecting the same top confidence/recency rows every turn.
- Stored noise from older extraction logic, such as one-off tool requests or search topics, is filtered out of prompt injection when possible. Those rows may still appear in the Preferences UI until manually deactivated/deleted.

The extraction path is intentionally automatic: there is no manual approval queue. The model is prompted to save durable memory only, such as explicit preferences, stable user facts, location hints, goals, background, or tools the user personally uses. It should ignore one-off requests like “tell me about Ollama,” “test Brave Search,” or “find latest movies.”

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Preference Extraction Process](#preference-extraction-process)
3. [Storage Architecture](#storage-architecture)
4. [Confidence Scores](#confidence-scores)
5. [API Endpoints](#api-endpoints)
6. [Memory Management](#memory-management)
7. [Frontend Integration](#frontend-integration)
8. [Examples](#examples)
9. [Best Practices](#best-practices)

## Core Concepts

### What is a User Preference?

A user preference is any piece of information about a user that might be relevant for future conversations. This includes:

- **Likes/Dislikes**: Things the user enjoys or doesn't enjoy
- **Expertise Areas**: Skills or knowledge the user possesses
- **Experience Levels**: How much experience the user has in certain areas
- **Goals**: What the user is trying to achieve
- **Challenges**: Problems the user is facing
- **Tools**: Technologies or tools the user works with
- **Learning Interests**: Topics the user wants to learn about
- **Personal Traits**: Characteristics of the user

### Preference Structure

Each preference consists of:

- **Type**: The category of preference (expertise, goal, like, etc.)
- **Value**: The specific information (Python programming, building web apps, etc.)
- **Confidence**: A score from 0.0 to 1.0 indicating how confident the system is
- **Context**: Why this preference was extracted
- **Metadata**: Additional information about when/where it was extracted

## Preference Extraction Process

### Step-by-Step Flow

1. **User Sends a Message**:
   - The message is received by the API or CLI interface
   - If a user_id is provided, the system will save preferences to the database

2. **Message Processing**:
   - The `add_user_message` method in `ChatBot` class processes the message
   - The message is added to the conversation history

3. **Preference Analysis**:
   - The `analyze_for_preferences` method is called
   - Recent conversation context is gathered (last 5 messages)
   - A prompt is constructed for the LLM to extract preferences

4. **LLM Analysis**:
   - The prompt is sent to the OpenAI API using a smaller model (default: gpt-4o-mini)
   - The LLM identifies potential preferences in the message
   - Each preference is assigned a confidence score
   - Only preferences with high confidence (typically >0.8) are returned

5. **Preference Storage**:
   - For each extracted preference:
     - A simplified version is added to message metadata as `preference: "{type} {value}"`
     - If a user_id is provided, the full preference is saved to the database
   - The message with metadata is saved to the conversation history table

6. **Response Generation**:
   - When generating a response, the system loads active preferences
   - Preferences are grouped by type and added to the system prompt
   - The LLM uses these preferences to personalize its response

### When Are Preferences Extracted?

Preferences are analyzed for **every user message**, but not every message will yield preferences. The system is designed to be conservative - it only extracts preferences when it's highly confident they represent genuine user traits or characteristics.

For example:
- "Hello" → No preferences extracted (generic greeting)
- "I've been working with Python for 5 years" → Preference extracted (expertise)
- "I'm trying to build a web application" → Preference extracted (goal)

## Storage Architecture

### Dual Storage Approach

The system uses a dual approach to storing preferences:

1. **Message Metadata**:
   - Each message can have a `preference` field in its metadata
   - Format: `"{type} {value}"` (e.g., "expertise Python")
   - Stored in the `conversation_history` table
   - Available even without a user_id
   - Limited to the conversation session

2. **User Preferences Database**:
   - Full preferences stored in the `user_preferences` table
   - Includes type, value, confidence, context, timestamps, etc.
   - Only saved if a user_id is provided
   - Persists across multiple sessions
   - Can be managed through API endpoints

### Database Schema

The `user_preferences` table has the following structure:

```sql
CREATE TABLE user_preferences (
  id SERIAL PRIMARY KEY,
  user_id TEXT NOT NULL,
  preference_type TEXT NOT NULL,
  preference_value TEXT NOT NULL,
  context TEXT,
  confidence FLOAT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  last_used TIMESTAMP WITH TIME ZONE,
  source_session TEXT,
  is_active BOOLEAN DEFAULT TRUE,
  metadata JSONB
);
```

### Smart Merging

When a preference similar to an existing one is detected:

1. The confidence score is updated to the maximum of the two scores
2. The context information is merged
3. The `last_used` timestamp is updated
4. Any new metadata is added to the existing metadata

This prevents duplicate preferences while enriching existing ones with new context.

## Confidence Scores

### What is a Confidence Score?

The confidence score is a value between 0.0 and 1.0 that indicates how certain the system is about a preference. It's determined by the LLM during preference extraction.

### Score Ranges

- **0.95 - 1.0**: Very high confidence - explicit statements (e.g., "I love Python")
- **0.85 - 0.94**: High confidence - strong implications (e.g., "I've been using Python daily for years")
- **0.75 - 0.84**: Moderate confidence - reasonable inferences (e.g., "I usually reach for Python when solving problems")
- **0.65 - 0.74**: Low confidence - possible but uncertain (e.g., "Python seems interesting")
- **< 0.65**: Very low confidence - typically not extracted

### How Scores Are Used

1. **Filtering**: By default, only preferences with confidence ≥ 0.7 are used in responses
2. **Prioritization**: Higher confidence preferences are given more weight
3. **Conflict Resolution**: When preferences conflict, the higher confidence one is preferred
4. **Retention**: Higher confidence preferences are more likely to be retained long-term

### Score Determination

The LLM determines confidence scores based on:

1. **Explicitness**: How directly the user stated the preference
2. **Consistency**: Whether it aligns with previous statements
3. **Recency**: More recent statements get higher confidence
4. **Specificity**: More specific statements get higher confidence

## API Endpoints

For authentication, rate limits, and the full HTTP surface (search, crawl, chat, sites, pages), see **[API.md](./API.md)**. Preference routes below are under **`/api/chat`** and follow the same auth rules as the rest of the API.

### Chat Defaults

```
GET /api/chat/defaults
```

Returns server-side defaults used by the web UI:

```json
{
  "user_id": "bigsk1",
  "profile": "default",
  "session_id": null
}
```

These values come from `CHAT_USER_ID`, `CHAT_PROFILE`, and `CHAT_SESSION_ID`.

### List User Preferences

```
GET /api/chat/preferences
```

**Query Parameters:**
- `user_id` (required): The user ID
- `min_confidence` (optional): Minimum confidence score (default: 0.0)
- `active_only` (optional): Whether to return only active preferences (default: true)
- `query` (optional): Rank preferences by relevance to a current question
- `limit` (optional): Maximum ranked preferences to return when `query` is provided

**Example:**
```bash
curl -X GET "http://localhost:8001/api/chat/preferences?user_id=TestUser&min_confidence=0.7&active_only=true"
```

Relevant-memory example:

```bash
curl -X GET "http://localhost:8001/api/chat/preferences?user_id=bigsk1&query=what%20movies%20are%20near%20me&min_confidence=0.7&limit=5"
```

**Response:**
```json
{
  "preferences": [
    {
      "id": 1,
      "preference_type": "expertise",
      "preference_value": "Python programming",
      "context": "User mentioned having 5 years of experience with Python",
      "confidence": 0.95,
      "created_at": "2025-03-13T15:42:39.433175+00:00",
      "updated_at": "2025-03-13T15:42:39.433175+00:00",
      "last_used": "2025-03-13T15:45:18.344413+00:00",
      "source_session": "test-session",
      "is_active": true,
      "metadata": {"message_content": "I have been working with Python for 5 years"}
    }
  ],
  "count": 1,
  "user_id": "TestUser"
}
```

### Create User Preference

```
POST /api/chat/preferences
```

**Query Parameters:**
- `user_id` (required): The user ID
- `session_id` (optional): Session ID

**Request Body:**
```json
{
  "preference_type": "like",
  "preference_value": "REST APIs",
  "context": "Manually added",
  "confidence": 0.9,
  "metadata": {"source": "manual_entry"}
}
```

**Example:**
```bash
curl -X POST "http://localhost:8001/api/chat/preferences?user_id=TestUser" \
  -H "Content-Type: application/json" \
  -d '{"preference_type":"like","preference_value":"REST APIs","context":"Manually added","confidence":0.9}'
```

**Response:**
```json
{
  "id": 2,
  "preference_type": "like",
  "preference_value": "REST APIs",
  "context": "Manually added",
  "confidence": 0.9,
  "created_at": "2025-03-13T16:00:00.000000+00:00",
  "updated_at": "2025-03-13T16:00:00.000000+00:00",
  "last_used": "2025-03-13T16:00:00.000000+00:00",
  "source_session": null,
  "is_active": true,
  "metadata": {"source": "manual_entry"}
}
```

### Deactivate User Preference

```
PUT /api/chat/preferences/{id}/deactivate
```

**Path Parameters:**
- `id` (required): The preference ID

**Example:**
```bash
curl -X PUT "http://localhost:8001/api/chat/preferences/2/deactivate"
```

**Response:**
```json
{
  "message": "Preference deactivated",
  "preference_id": 2
}
```

### Delete User Preference

```
DELETE /api/chat/preferences/{id}
```

**Path Parameters:**
- `id` (required): The preference ID

**Example:**
```bash
curl -X DELETE "http://localhost:8001/api/chat/preferences/2"
```

**Response:**
```json
{
  "message": "Preference deleted",
  "preference_id": 2
}
```

### Clear All User Preferences

```
DELETE /api/chat/preferences
```

**Query Parameters:**
- `user_id` (required): The user ID

**Example:**
```bash
curl -X DELETE "http://localhost:8001/api/chat/preferences?user_id=TestUser"
```

**Response:**
```json
{
  "message": "All preferences cleared for user TestUser",
  "user_id": "TestUser"
}
```

## Memory Management

### Preference Limits

The system does not have a hard limit on the number of preferences it can store for a user. However, there are practical considerations:

1. **Token Limits**: The LLM has a context window limit (typically 8K-32K tokens)
2. **Relevance Decay**: Older preferences may become less relevant over time
3. **System Prompt Size**: Too many preferences can make the system prompt unwieldy

### How Many Preferences Are Used?

When generating responses, the system:

1. Retrieves all active preferences with confidence ≥ 0.7
2. Updates the `last_used` timestamp for each preference
3. Groups preferences by type
4. Adds them to the system prompt

There is no fixed limit, but in practice:
- Most users will have 5-20 active preferences
- The system prompt can comfortably handle 30-50 preferences
- Beyond that, performance may degrade due to token limits

### Long-Term Memory

Preferences are designed to be long-term memory. A preference expressed a month ago will still be available if:

1. The same user_id is used
2. The preference has not been deactivated or deleted
3. The preference had a high confidence score

### Preference Lifecycle

1. **Creation**: Extracted from conversation or manually added
2. **Usage**: Retrieved and used in system prompts
3. **Updates**: Merged with similar preferences, confidence potentially increased
4. **Deactivation**: Marked as inactive (soft delete)
5. **Deletion**: Permanently removed from the database

### Automatic Preference Management

Currently, the system does not automatically prune or deactivate preferences. This is a potential area for future enhancement:

- Automatically deactivate preferences not used for X months
- Reduce confidence of preferences over time
- Implement a preference conflict resolution system
- Add preference versioning to track changes

## CLI Commands

The chat interface includes several commands for managing user preferences directly from the command line:

### Viewing Preferences

```
preferences
```

Displays a table of all active preferences for the current user, including:
- ID
- Type
- Value
- Confidence
- Context
- Last Used timestamp

### Adding Preferences

```
add preference <type> <value> [confidence]
```

Manually adds a new preference for the current user.

**Examples:**
```
add preference like Python
add preference expertise JavaScript 0.85
add preference goal "Learn machine learning"
```

If confidence is not specified, it defaults to 0.9.

### Deleting Preferences

```
delete preference <id>
```

Deletes a specific preference by ID.

**Example:**
```
delete preference 5
```

### Clearing All Preferences

```
clear preferences
```

Deletes all preferences for the current user after confirmation.

### Help

```
help
```

Displays a list of all available commands, including the preference management commands.

### Important Notes

- Preference commands are only available when a user ID is provided (using `--user` when starting the chat).
- If no user ID is provided, the system will display a message explaining that preferences are only stored for identified users.
- Preferences added via CLI are marked with the context "Manually added via CLI" and include metadata indicating they were manually added.

## Frontend Integration

*[Placeholder for frontend integration details]*

This section will cover:
- How to display user preferences in the UI
- Preference management interface
- Visual indicators for preference usage
- Real-time preference updates

## Examples

### Example 1: Extracting Multiple Preferences

**User Message:**
```
I have been working as a software engineer for 5 years, mostly with backend systems. I am trying to learn more about frontend development because I want to build full-stack applications.
```

**Extracted Preferences:**
```json
[
  {
    "preference_type": "experience",
    "preference_value": "5 years in software engineering",
    "confidence": 0.95,
    "context": "User mentioned having 5 years of experience as a software engineer"
  },
  {
    "preference_type": "expertise",
    "preference_value": "backend systems",
    "confidence": 0.9,
    "context": "User has mostly worked with backend systems"
  },
  {
    "preference_type": "learning interest",
    "preference_value": "frontend development",
    "confidence": 0.9,
    "context": "User is trying to learn more about frontend development"
  },
  {
    "preference_type": "goal",
    "preference_value": "building full-stack applications",
    "confidence": 0.85,
    "context": "User wants to build full-stack applications"
  }
]
```

### Example 2: Using Preferences in Responses

**User Query:**
```
What technologies should I focus on learning next?
```

**System Prompt (with preferences):**
```
You are acting according to this profile: technical

[Technical profile system prompt...]

The user's name is TestUser.

The current date is Wednesday, March 13, 2025 and the time is 04:05 PM.

User information from previous conversations:

Experience:
- 5 years in software engineering (confidence: 0.95) - User mentioned having 5 years of experience as a software engineer

Expertise:
- backend systems (confidence: 0.90) - User has mostly worked with backend systems
- Python programming (confidence: 0.95) - User explicitly stated they enjoy Python programming

Learning interest:
- frontend development (confidence: 0.90) - User is trying to learn more about frontend development

Goal:
- building full-stack applications (confidence: 0.85) - User wants to build full-stack applications

Like:
- TypeScript (confidence: 0.95) - User stated they enjoy working with TypeScript
- REST APIs (confidence: 0.90) - Manually added

Dislike:
- JavaScript (confidence: 0.95) - User explicitly stated they dislike JavaScript
- Ruby (confidence: 0.95) - User finds Ruby confusing, indicating a dislike or difficulty with it

[Rest of system prompt...]
```

**Response:**
```
Since you're interested in learning more about frontend development and enjoy working with TypeScript, focusing on technologies that complement these interests would be beneficial. Here are a few suggestions:

1. **React**: A popular JavaScript library for building user interfaces. It has a strong community and ecosystem, and you can use it with TypeScript for type safety.

2. **Angular**: A platform and framework for building single-page client applications using HTML and TypeScript. Since you enjoy TypeScript, Angular might be a good fit.

3. **Vue.js**: Another progressive JavaScript framework for building user interfaces. It is known for its simplicity and flexibility, and you can use it with TypeScript as well.

4. **CSS Frameworks**: Learning a CSS framework like Bootstrap or Tailwind CSS can help you design responsive and visually appealing interfaces quickly.

5. **Frontend Tools**: Familiarize yourself with tools like Webpack, Babel, and ESLint, which are commonly used in frontend development for bundling, transpiling, and linting code.

These technologies should give you a strong foundation in frontend development and help you build full-stack applications. Let me know if you need more detailed information on any of these!
```

## Best Practices

### When to Use User Preferences

1. **Long-term Users**: For users who will have multiple conversations over time
2. **Personalized Experiences**: When customization based on user traits is important
3. **Technical Support**: To remember user's technical environment and skills
4. **Learning Platforms**: To track user's progress and interests

### When Not to Use User Preferences

1. **Anonymous Chats**: For one-off conversations with anonymous users
2. **Privacy-Sensitive Contexts**: When storing user information raises privacy concerns
3. **Simple Q&A Systems**: For basic question-answering without personalization

### Tips for Effective Preference Management

1. **Use Consistent User IDs**: Ensure the same user_id is used across sessions
2. **Balance Specificity**: Too general preferences aren't useful, too specific ones don't apply broadly
3. **Regular Cleanup**: Periodically review and clean up outdated preferences
4. **Preference Hierarchy**: Organize preferences in a logical hierarchy by type
5. **Confidence Thresholds**: Adjust min_confidence based on your application's needs

### Security and Privacy Considerations

1. **Data Minimization**: Only store preferences that provide value
2. **User Control**: Allow users to view and manage their stored preferences
3. **Transparency**: Be clear about what information is being stored
4. **Data Protection**: Implement appropriate security measures for user data
5. **Compliance**: Ensure compliance with relevant privacy regulations
