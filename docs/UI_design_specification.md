# CapiLearn UI Design Specification

## Purpose

Describe the frontend UI structure, page responsibilities, design language, and current implementation status for CapiLearn.

## Design Goals

- Keep the interface calm, student-friendly, and non-intimidating
- Support guided learning rather than direct answer delivery
- Separate student, instructor, and administrator concerns
- Make operational/admin data easy to scan
- Keep frontend pages modular and easy to connect to backend APIs

## Visual Style

- Warm cream background
- Green primary action color
- Rounded cards and soft borders
- Calm mascot-driven branding
- Dashboard layouts with clear cards, panels, and tables

## Page Structure

### Landing Page

Route: `/`

Purpose:

- Introduce CapiLearn
- Provide navigation to major app areas
- Present the brand and core value proposition

Primary actions:

- Student Workspace
- Instructor Dashboard
- Administrator Dashboard

### Learning Workspace

Route: `/workspace`

Purpose:

- Main student chat interface
- Allows students to ask questions and receive guided assistance
- Supports conversation history, message loading, markdown rendering, and message search

Implemented features:

- Conversation sidebar
- New conversation reset
- Send message to backend
- Load previous conversation messages
- Markdown rendering for assistant responses
- Search current conversation messages
- Highlight matching search terms
- Prevent stale async responses from appearing in the wrong conversation

### Student Dashboard

Route: `/student-dashboard`

Purpose:

- Student-facing learning progress overview

Current status:

- Static/front-end layout placeholder

### Instructor Dashboard

Route: `/instructor-dashboard`

Purpose:

- Instructor-facing learning insights
- Focuses on student activity, learning friction, and question trends

Should not include:

- System health
- Admin operations
- Infrastructure status

### Administrator Dashboard

Route: `/admin-dashboard`

Purpose:

- Admin-facing operational dashboard
- Shows platform usage and system-level information

Implemented features:

- Live usage summary from `GET /api/admin/usage/summary`
- Total users
- Conversations
- User queries
- Assistant responses
- Failed/blocked responses
- Tokens, cost, and latency metrics

Planned features:

- Real system health checks from `GET /api/admin/system-health`
- Recent interactions table
- Ingestion status
- More detailed operational logs

## User Roles

### Student

Uses:

- Landing Page
- Learning Workspace
- Student Dashboard

### Instructor

Uses:

- Instructor Dashboard
- Student learning activity views

### Administrator

Uses:

- Administrator Dashboard
- System health and usage views

## Frontend Services

### `conversationService.js`

Handles:

- Listing conversations
- Creating conversations
- Loading conversation messages
- Sending follow-up messages

### `adminService.js`

Handles:

- Loading admin usage summary data
- Future admin system health data

### `apiClient.js`

Handles:

- Shared API base URL
- Centralized response parsing
- Centralized frontend API error handling

## API Integration

Current backend integrations:

- `GET /api/conversations`
- `POST /api/conversations`
- `GET /api/conversations/:id/messages`
- `POST /api/conversations/:id/messages`
- `GET /api/admin/usage/summary`

Planned backend integrations:

- `GET /api/admin/system-health`

## UI State Behavior

### Chat Race Condition Prevention

The Learning Workspace uses an active conversation ref to prevent stale async responses from updating the wrong conversation view.

Expected behavior:

- If a user sends a message in Conversation A and switches to Conversation B before the response returns, Conversation A’s response must not appear in Conversation B.
- If a user quickly switches conversations while messages are loading, older responses must not overwrite the currently selected conversation.

### Chat Search

Current behavior:

- Searches the current conversation only
- Filters visible messages
- Highlights matching terms
- Displays match count
- Clears search when switching conversations or starting a new conversation

## Accessibility Notes

Future improvements:

- Better keyboard navigation
- Clear focus states
- ARIA labels for icon-only controls
- Improved screen-reader labeling for dashboard cards and status indicators

## Future UI Work

- Auth-aware routing
- Protected student/instructor/admin pages
- Fully dynamic instructor dashboard
- Real admin system health checks
- Recent admin interaction logs
- Responsive sidebar improvements
- Better empty/loading/error states