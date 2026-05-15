// ESLint config for the bare RN app. Includes hexagonal layer enforcement.
module.exports = {
  root: true,
  extends: [
    '@react-native',
    'plugin:@typescript-eslint/recommended',
    'plugin:boundaries/recommended',
  ],
  plugins: ['boundaries', '@typescript-eslint'],
  parser: '@typescript-eslint/parser',
  parserOptions: { project: './tsconfig.json' },
  settings: {
    'boundaries/elements': [
      { type: 'domain',         pattern: 'src/domain/*' },
      { type: 'application',    pattern: 'src/application/*' },
      { type: 'infrastructure', pattern: 'src/infrastructure/*' },
      { type: 'delivery',       pattern: 'src/delivery/*' },
      { type: 'fakes',          pattern: 'src/fakes/*' },
    ],
  },
  rules: {
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    '@typescript-eslint/consistent-type-imports': 'error',

    // Hexagonal boundary enforcement.
    'boundaries/element-types': ['error', {
      default: 'disallow',
      rules: [
        { from: 'domain',         allow: ['domain'] },
        { from: 'application',    allow: ['domain', 'application'] },
        { from: 'infrastructure', allow: ['domain', 'application', 'infrastructure'] },
        { from: 'delivery',       allow: ['domain', 'application', 'delivery'] },
        { from: 'fakes',          allow: ['domain', 'application', 'fakes'] },
      ],
    }],
  },
};
