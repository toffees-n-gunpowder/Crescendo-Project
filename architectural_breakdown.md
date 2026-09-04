# Crescendo Project: Architectural Breakdown

This document provides a comprehensive architectural analysis of the Crescendo project workspace, specifically detailing its transition from the Django ORM to 100% raw SQL, and mapping its components to the CSE 216 60% Milestone guidelines.

## 1. File-by-File Inventory

Now that the Django ORM has been removed, the core architecture leans on raw database cursors and custom service/auth layers.

*   **`music/models.py`**: This file has been functionally emptied to comply with the raw SQL requirement. It no longer contains declarative Django models or database schema definitions. 
*   **`music/views.py`, `music/views_artist.py`, `music/views_artistpage.py`**: These contain the core application logic. Instead of relying on `Model.objects.all()`, view functions utilize `django.db.connection.cursor()` to manually query the PostgreSQL/NeonDB database, extracting results via custom utility functions like `dictfetchall`.
*   **`music/urls.py` & `crescendo_config/urls.py`**: These handle HTTP request routing. They map incoming paths and RESTful endpoints (e.g., `/login/`, `/like/<int:track_id>/`) to their respective view handlers.
*   **`music/auth/` Directory**: 
    *   **`users.py`**: Manages the raw SQL logic for user registration, authentication, and user retrieval.
    *   **`hashing.py`**: Implements secure, salted password hashing (e.g., using bcrypt/argon2) to meet credential storage requirements.
    *   **`sessions.py`**: Manages session state via raw queries to a custom sessions table, ensuring login state is securely stored and tokenized (as opposed to Django's built-in session engine).
    *   **`decorators.py`**: Contains crucial access control logic, such as `@login_required` and `@role_required` wrappers that enforce authorization before a view is executed.
    *   **`middleware.py`**: Intercepts requests early in the lifecycle to validate session tokens and attach the authenticated `user` object to the `request` before it hits the view layer.
*   **`music/db/` Directory (e.g., `catalog.py`, `playlists.py`)**: Dedicated data access objects (DAOs) containing complex raw SQL operations to keep the view layer cleaner.
*   **`music/templates/`**: Contains the HTML templates that drive the frontend, dynamically rendering forms, tables, and actions based on the backend data.

## 2. End-to-End Workflow

Here is the lifecycle of a request, demonstrating how data flows through the system without the ORM:

1.  **Request Initiation**: The user's browser triggers an action (e.g., clicking "Like" on a track).
2.  **Routing (`urls.py`)**: The request is routed to a specific endpoint (e.g., `path('like/<int:track_id>/', views.toggle_like, name='toggle_like')`).
3.  **Middleware & Authentication (`music/auth/middleware.py`)**: The custom middleware inspects the request cookies for a session token. It queries the raw SQL session table to validate the token. If valid, it attaches the `request.user` to the session.
4.  **Authorization Checks (`music/auth/decorators.py`)**: If the view requires specific access (e.g., `@login_required`), the decorator validates the `request.user`. If unauthorized, it immediately terminates the request with a `401 Unauthorized` or `403 Forbidden` response.
5.  **Controller Logic (`views.py`)**: The view function executes.
6.  **Raw SQL Execution (`django.db.connection`)**: The view opens a database cursor:
    ```python
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM music_likedtrack WHERE user_id = %s AND track_id = %s;", [request.user.id, track_id])
    ```
7.  **Data Extraction**: The cursor's raw tuple outputs are converted to accessible dictionaries (e.g., using `dictfetchall()`).
8.  **Response Generation**: The view renders a template (passing the raw data dictionary) or returns a JSON response, completing the cycle back to the frontend.

## 3. Requirements Mapping (CSE 216 60% Milestone)

### 3.1 Authentication
*   **Sign-up and Login**: Implemented via `register_user` and `login_user` in `music/views.py`. These views process input forms and delegate logic to `music/auth/users.py`, which executes raw `INSERT` and `SELECT` queries for validation.
*   **Credential Storage**: Managed by `music/auth/hashing.py`, which ensures passwords are encrypted using a standard algorithm with a per-user salt before being inserted via raw SQL.
*   **Session Management & Logout**: Implemented in `music/auth/sessions.py`. Login generates a signed token stored securely, and logout triggers `sessions.destroy()` which physically deletes or invalidates the token in the database.
*   **Validation**: The `forms.py` file validates inputs, and `views.py` returns specific status codes (e.g., `400` for bad input, `409` for duplicate username/email, `401` for incorrect credentials).

### 3.2 Authorization & Role Separation
*   **Server-Side Enforcement**: Role validation is strictly enforced on the backend via decorators like `@role_required` in `music/auth/decorators.py`. It does not rely on frontend logic.
*   **Blocking Cross-Role Access**: Attempting to access an Admin or Artist view as a Standard User will trigger a `403 Forbidden` error because the decorator checks the role stored in the database.
*   **Object-Level Ownership Checks**: Views are structured to append ownership checks directly into the SQL statement. For example, querying a playlist includes `WHERE user_id = %s` tied to `request.user.id`, ensuring a user cannot spoof `playlist_id` to manipulate another user's data.

### 3.3 HTTP/API Endpoints & SQL Safety
*   **REST Conventions**: Views use proper HTTP methods (checking `request.method == 'POST'` vs `GET`) and respond with appropriate HTTP status codes like `200`, `400`, `401`, `404` (via `Http404`), and `409`.
*   **SQL Safety (Parameterized Queries)**: The application prevents SQL injection by strictly utilizing parameterized queries provided by `psycopg2`/Django connections. String concatenation is completely avoided:
    *   **Safe**: `cursor.execute("SELECT * FROM table WHERE id = %s;", [user_id])`
    *   **Unsafe**: `cursor.execute(f"SELECT * FROM table WHERE id = {user_id};")` (This anti-pattern is avoided).

### 3.4 Minimal Frontend
*   **Role-Aware Interface**: Templates within `music/templates/` use condition checks (e.g., `{% if user.role == 'admin' %}`) to render specialized navigation menus or buttons (like "Admin Panel" or "Studio").
*   **Feature Access & Error Feedback**: The frontend provides HTML forms (like login, registration, upload) wired directly to backend API routes. Server-side errors and validation messages are presented back to the user via Django's `messages` framework, rather than silently failing.
