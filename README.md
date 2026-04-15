# Building a user registration API

## Context

Dailymotion handles user registrations. To do so, user creates an account and we send a code by email to verify the account.

As a core API developer, you are responsible for building this feature and expose it through API.

## Specifications
You have to manage a user registration and his activation.

The API must support the following use cases:
* Create a user with an email and a password.
* Send an email to the user with a 4 digits code.
* Activate this account with the 4 digits code received. For this step, we consider a `BASIC AUTH` is enough to check if he is the right user.
* The user has only one minute to use this code. After that, an error should be raised.

Design and build this API. You are completely free to propose the architecture you want.

## What do we expect?
- Python language is required.
- We expect to have a level of code quality which could go to production.

### Framework & Architecture
- **FastAPI framework is mandatory**. This is our production stack and we need to evaluate your mastery of:
  - Async/await patterns
  - Dependency Injection (FastAPI Depends)
  - Pydantic validation (request/response models)
  - Exception handlers
  - Lifespan events (startup/shutdown)

### Libraries constraints
- You can use libraries for specific utilities: db connection pooling (asyncpg, psycopg), testing (pytest), validation (pydantic), etc.
- **No ORMs allowed** (including SQLAlchemy, Tortoise ORM, etc.). We want to see **your** implementation of business logic and data access layers.

### Other requirements
- Use the DBMS you want (except SQLite).
- Consider the SMTP server as a third party service offering an HTTP API. You can mock the call, use a local SMTP server running in a container, or simply print the 4 digits in console. But do not forget in your implementation that **it is a third party service**.
- Your code should be tested.
- Your application has to run within docker containers.
- You can use AI to help you, but in a smart way. However, please make iterative commits as we analyze them to understand your development reasoning (not all the code in 1 or 2 commits).
- You should provide us the link to GitHub.
- You should provide us the instructions to run your code and your tests. We should not install anything except docker/docker-compose to run your project.
- You should provide us an architecture schema.