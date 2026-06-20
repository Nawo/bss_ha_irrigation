#!/bin/bash
echo "================================================="
echo "  Starting Irrigation BSS in Local Mock Mode"
echo "================================================="

# Go to the directory of this script to ensure relative paths work
cd "$(dirname "$0")" || exit 1

# 1. Prerequisite checks
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is required but not installed."
    exit 1
fi

if ! command -v npm &> /dev/null; then
    echo "Error: npm is required but not installed."
    exit 1
fi

# 2. Setup backend
echo "[1/2] Setting up Backend..."
cd backend || exit 1

# Create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt > /dev/null

# Environment variables for mock mode
export MOCK_HA=1
export DATA_DIR="../data"
export LOG_LEVEL="debug"
mkdir -p "$DATA_DIR"

echo "-> Starting Uvicorn backend on http://localhost:8099"
uvicorn main:app --reload --port 8099 &
BACKEND_PID=$!
cd ..

# 3. Setup frontend
echo "[2/2] Setting up Frontend..."
cd frontend || exit 1

echo "Installing npm dependencies (if any missing)..."
npm install > /dev/null

echo "-> Starting Vite dev server..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "================================================="
echo " ✅ Both servers are running!"
echo " 🌐 Backend:  http://localhost:8099"
echo " 💻 Frontend: Check the Vite URL above (usually http://localhost:5173)"
echo " 🛑 Press Ctrl+C to stop both servers."
echo "================================================="

# Wait for signals to kill both processes
trap "echo 'Shutting down servers...'; kill $BACKEND_PID $FRONTEND_PID; exit" SIGINT SIGTERM
wait
