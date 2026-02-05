# PostgreSQL + pgvector Installation Guide (Development - Windows)

This guide covers the installation of PostgreSQL 18 and the pgvector extension for local development on Windows.

## Prerequisites

Before installing pgvector, ensure you have:

1. **Git** - For cloning the pgvector repository
2. **Visual Studio C++ Build Tools** - Required for compiling pgvector
   - Check if you have it by looking for "x64 Native Tools Command Prompt" in your Start menu
   - If not installed, download Visual Studio from [https://visualstudio.microsoft.com/downloads/](https://visualstudio.microsoft.com/downloads/)

## Step 1: Install PostgreSQL 18

1. Download PostgreSQL 18 from the official installer: [https://www.postgresql.org/download/](https://www.postgresql.org/download/)
2. During installation, ensure you include:
   - StackBuilder
   - pgAdmin 4
   - Command Line Tools

## Step 2: Install pgvector Extension

### 2.1 Open x64 Native Tools Command Prompt

1. From your Start menu, search for "x64 Native Tools Command Prompt for VS [version]"
2. **Run as Administrator**

### 2.2 Set the PGROOT Environment Variable

This informs the build process where PostgreSQL is installed. Replace the path with your actual PostgreSQL installation path if different:

```cmd
set "PGROOT=C:\Program Files\PostgreSQL\18"
```

### 2.3 Clone the pgvector Repository

Navigate to a temporary directory and clone the pgvector source code:

```cmd
cd %TEMP%
git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git
cd pgvector
```

### 2.4 Compile pgvector

Use the provided Windows makefile to compile the library:

```cmd
nmake /F Makefile.win
```

### 2.5 Install pgvector

Install the compiled extension:

```cmd
nmake /F Makefile.win install
```

You should see output indicating that files (like `vector.dll`, `vector.control`, etc.) are being copied to the appropriate `lib` and `share/extension` folders within your PostgreSQL installation directory (`%PGROOT%`).

## Step 3: Configure pgAdmin 4

### 3.1 Add a Server (if not already configured)

1. Open **pgAdmin 4**
2. Right-click on "Servers" and select "Register" > "Server"
3. In the **General** tab:
   - Name: `Local PostgreSQL` (or any name you prefer)
4. In the **Connection** tab:
   - Host name/address: `localhost`
   - Port: `5432`
   - Maintenance database: `postgres`
   - Username: `postgres`
   - Password: (enter the password you set during PostgreSQL installation)
5. Click **Save**

You should now see a "postgres" database, which is the default database suitable for local development.

### 3.2 Enable the pgvector Extension

1. In pgAdmin 4, navigate to your server > Databases > **postgres**
2. Right-click on **postgres** and select "Query Tool"
3. Run the following SQL command:

```sql
CREATE EXTENSION vector;
```

### 3.3 Verify Installation

To verify that pgvector has been successfully enabled, run:

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
```

You should see output showing the `vector` extension and its version.

## Next Steps

You can now:
- Create tables with `VECTOR(n)` columns
- Insert embeddings
- Run similarity searches within this database

## Troubleshooting

- If you encounter compilation errors, ensure Visual Studio C++ Build Tools are properly installed
- Verify that the `PGROOT` path matches your actual PostgreSQL installation directory
- Make sure you're running the x64 Native Tools Command Prompt as Administrator
