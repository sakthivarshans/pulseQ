-- NeuralOps seed data — default repositories shown to all users
-- Runs after init.sql via docker-entrypoint-initdb.d

INSERT INTO repositories (id, name, owner, url, description, language, platform, is_default)
VALUES
  (
    'aaaaaaaa-0001-0001-0001-aaaaaaaaaaaa',
    'sample-nodejs-webapp',
    'neuralops-examples',
    'https://github.com/neuralops-examples/sample-nodejs-webapp',
    'Example Node.js Express web application demonstrating NeuralOps monitoring',
    'JavaScript',
    'github',
    TRUE
  ),
  (
    'aaaaaaaa-0002-0002-0002-aaaaaaaaaaaa',
    'sample-fastapi-service',
    'neuralops-examples',
    'https://github.com/neuralops-examples/sample-fastapi-service',
    'Example Python FastAPI microservice with async endpoints and SQLAlchemy',
    'Python',
    'github',
    TRUE
  ),
  (
    'aaaaaaaa-0003-0003-0003-aaaaaaaaaaaa',
    'sample-react-frontend',
    'neuralops-examples',
    'https://github.com/neuralops-examples/sample-react-frontend',
    'Example React + TypeScript frontend application with Vite build tooling',
    'TypeScript',
    'github',
    TRUE
  )
ON CONFLICT (id) DO NOTHING;
