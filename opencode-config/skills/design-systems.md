# Skill: Design Systems
# Loaded on-demand when task involves design tokens, component libraries, Storybook, theming, or component API design

## Auto-Detect

Trigger this skill when:
- Task mentions: design system, design tokens, Storybook, component library, theming, variants
- Files: `tokens/`, `*.stories.tsx`, `.storybook/`, `theme.*`, `design-system/`
- Patterns: component API design, variant patterns, accessibility in components
- `package.json` contains: `storybook`, `@radix-ui/*`, `class-variance-authority`, `@vanilla-extract/*`

---

## Decision Tree: Design System Scope

```
What level of design system do you need?
+-- Just consistent styling?
|   +-- Design tokens + utility CSS (Tailwind) -> No component library needed
+-- Shared components within one app?
|   +-- Local component library (src/components/) -> No package needed
+-- Shared across multiple apps (same team)?
|   +-- Internal package (@acme/ui) -> Monorepo workspace package
+-- Shared across teams/orgs?
|   +-- Published package + Storybook docs + versioning
+-- Building on top of existing primitives?
    +-- Radix UI / Headless UI (unstyled) + your design tokens
```

## Decision Tree: Styling Approach

```
+-- Need zero-runtime CSS? -> Vanilla Extract / Panda CSS / Tailwind
+-- Need runtime theming (user-switchable)? -> CSS variables + Tailwind
+-- Need CSS-in-JS with TypeScript? -> Vanilla Extract (build-time)
+-- Need maximum flexibility? -> Tailwind + CVA (class-variance-authority)
+-- Need scoped styles in components? -> CSS Modules or Vanilla Extract
```

---

## Design Tokens

```typescript
// tokens/colors.ts — Single source of truth
export const colors = {
  // Primitive tokens (raw values)
  primitive: {
    blue: {
      50: '#eff6ff',
      100: '#dbeafe',
      200: '#bfdbfe',
      300: '#93c5fd',
      400: '#60a5fa',
      500: '#3b82f6',
      600: '#2563eb',
      700: '#1d4ed8',
      800: '#1e40af',
      900: '#1e3a8a',
    },
    gray: {
      50: '#f9fafb',
      100: '#f3f4f6',
      200: '#e5e7eb',
      300: '#d1d5db',
      400: '#9ca3af',
      500: '#6b7280',
      600: '#4b5563',
      700: '#374151',
      800: '#1f2937',
      900: '#111827',
    },
    // ... other color scales
  },

  // Semantic tokens (purpose-driven, theme-aware)
  semantic: {
    light: {
      background: { DEFAULT: '#ffffff', subtle: '#f9fafb', muted: '#f3f4f6' },
      foreground: { DEFAULT: '#111827', muted: '#6b7280', subtle: '#9ca3af' },
      primary: { DEFAULT: '#2563eb', hover: '#1d4ed8', foreground: '#ffffff' },
      destructive: { DEFAULT: '#dc2626', hover: '#b91c1c', foreground: '#ffffff' },
      border: { DEFAULT: '#e5e7eb', focus: '#2563eb' },
      ring: '#2563eb',
    },
    dark: {
      background: { DEFAULT: '#0f172a', subtle: '#1e293b', muted: '#334155' },
      foreground: { DEFAULT: '#f8fafc', muted: '#94a3b8', subtle: '#64748b' },
      primary: { DEFAULT: '#3b82f6', hover: '#60a5fa', foreground: '#ffffff' },
      destructive: { DEFAULT: '#ef4444', hover: '#f87171', foreground: '#ffffff' },
      border: { DEFAULT: '#334155', focus: '#3b82f6' },
      ring: '#3b82f6',
    },
  },
} as const;

// tokens/spacing.ts
export const spacing = {
  0: '0px',
  0.5: '2px',
  1: '4px',
  1.5: '6px',
  2: '8px',
  3: '12px',
  4: '16px',
  5: '20px',
  6: '24px',
  8: '32px',
  10: '40px',
  12: '48px',
  16: '64px',
  20: '80px',
} as const;

// tokens/typography.ts
export const typography = {
  fontFamily: {
    sans: ['Inter', 'system-ui', 'sans-serif'],
    mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
  },
  fontSize: {
    xs: ['0.75rem', { lineHeight: '1rem' }],
    sm: ['0.875rem', { lineHeight: '1.25rem' }],
    base: ['1rem', { lineHeight: '1.5rem' }],
    lg: ['1.125rem', { lineHeight: '1.75rem' }],
    xl: ['1.25rem', { lineHeight: '1.75rem' }],
    '2xl': ['1.5rem', { lineHeight: '2rem' }],
    '3xl': ['1.875rem', { lineHeight: '2.25rem' }],
  },
} as const;
```

### CSS Variables from Tokens

```typescript
// Generate CSS custom properties from tokens
function tokensToCSSVariables(tokens: Record<string, any>, prefix = ''): string {
  const lines: string[] = [];

  for (const [key, value] of Object.entries(tokens)) {
    const varName = prefix ? `${prefix}-${key}` : key;

    if (typeof value === 'object' && !Array.isArray(value)) {
      lines.push(tokensToCSSVariables(value, varName));
    } else {
      lines.push(`  --${varName}: ${value};`);
    }
  }

  return lines.join('\n');
}

// Output: CSS file with theme variables
// :root { --color-primary: #2563eb; ... }
// [data-theme="dark"] { --color-primary: #3b82f6; ... }
```

---

## Component API Design

```typescript
// Principle: Composition over configuration
// Use slots/children instead of dozens of props

import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from '@radix-ui/react-slot';
import { forwardRef } from 'react';
import { cn } from '@/lib/utils';

// Button — well-designed component API
const buttonVariants = cva(
  // Base styles (always applied)
  'inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground hover:bg-destructive/90',
        outline: 'border border-input bg-background hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
        icon: 'h-10 w-10',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;  // Render as child element (Slot pattern)
  loading?: boolean;
}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button';

    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <>
            <Spinner className="mr-2 h-4 w-4 animate-spin" />
            {children}
          </>
        ) : (
          children
        )}
      </Comp>
    );
  }
);
Button.displayName = 'Button';

export { Button, buttonVariants };
```

### Compound Component Pattern

```typescript
// For complex components: use compound pattern
// Usage: <Card><Card.Header>...</Card.Header><Card.Body>...</Card.Body></Card>

interface CardContextValue {
  variant: 'default' | 'outlined' | 'elevated';
}

const CardContext = React.createContext<CardContextValue>({ variant: 'default' });

function Card({ variant = 'default', className, children, ...props }: CardProps) {
  return (
    <CardContext.Provider value={{ variant }}>
      <div
        className={cn(
          'rounded-lg border bg-card text-card-foreground',
          variant === 'elevated' && 'shadow-md',
          variant === 'outlined' && 'border-2',
          className
        )}
        {...props}
      >
        {children}
      </div>
    </CardContext.Provider>
  );
}

Card.Header = function CardHeader({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex flex-col space-y-1.5 p-6', className)} {...props}>
      {children}
    </div>
  );
};

Card.Title = function CardTitle({ className, children, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn('text-2xl font-semibold leading-none tracking-tight', className)} {...props}>
      {children}
    </h3>
  );
};

Card.Content = function CardContent({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('p-6 pt-0', className)} {...props}>
      {children}
    </div>
  );
};

Card.Footer = function CardFooter({ className, children, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex items-center p-6 pt-0', className)} {...props}>
      {children}
    </div>
  );
};
```

---

## Storybook Configuration

```typescript
// .storybook/main.ts
import type { StorybookConfig } from '@storybook/react-vite';

const config: StorybookConfig = {
  stories: ['../src/**/*.stories.@(ts|tsx)'],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-a11y',        // Accessibility checks
    '@storybook/addon-interactions', // Interaction testing
    '@chromatic-com/storybook',      // Visual regression
  ],
  framework: '@storybook/react-vite',
};

export default config;
```

```typescript
// src/components/button/button.stories.tsx
import type { Meta, StoryObj } from '@storybook/react';
import { fn } from '@storybook/test';
import { Button } from './button';

const meta: Meta<typeof Button> = {
  title: 'Components/Button',
  component: Button,
  parameters: {
    layout: 'centered',
    docs: {
      description: {
        component: 'Primary action button with multiple variants and sizes.',
      },
    },
  },
  tags: ['autodocs'],
  argTypes: {
    variant: {
      control: 'select',
      options: ['default', 'destructive', 'outline', 'secondary', 'ghost', 'link'],
    },
    size: {
      control: 'select',
      options: ['default', 'sm', 'lg', 'icon'],
    },
  },
  args: {
    onClick: fn(),
  },
};

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: { children: 'Button' },
};

export const Destructive: Story = {
  args: { children: 'Delete', variant: 'destructive' },
};

export const Loading: Story = {
  args: { children: 'Saving...', loading: true },
};

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap gap-4">
      <Button variant="default">Default</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="destructive">Destructive</Button>
      <Button variant="outline">Outline</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="link">Link</Button>
    </div>
  ),
};

// Interaction test
export const ClickTest: Story = {
  args: { children: 'Click me' },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button'));
    expect(args.onClick).toHaveBeenCalledTimes(1);
  },
};
```

---

## Accessibility in Components

```typescript
// Accessible component checklist (built into every component)

// 1. Keyboard navigation
// - All interactive elements focusable
// - Tab order follows visual order
// - Escape closes overlays
// - Arrow keys for lists/menus

// 2. ARIA attributes
function Dialog({ open, onClose, title, children }: DialogProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="dialog-title"
      aria-describedby="dialog-description"
      tabIndex={-1}
    >
      <h2 id="dialog-title">{title}</h2>
      <div id="dialog-description">{children}</div>
      <button onClick={onClose} aria-label="Close dialog">X</button>
    </div>
  );
}

// 3. Color contrast (WCAG AA minimum)
// - Normal text: 4.5:1 contrast ratio
// - Large text (18px+ or 14px+ bold): 3:1
// - UI components: 3:1

// 4. Focus management
function useFocusTrap(ref: React.RefObject<HTMLElement>) {
  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const focusableElements = element.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusableElements[0] as HTMLElement;
    const last = focusableElements[focusableElements.length - 1] as HTMLElement;

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key !== 'Tab') return;

      if (e.shiftKey) {
        if (document.activeElement === first) {
          last.focus();
          e.preventDefault();
        }
      } else {
        if (document.activeElement === last) {
          first.focus();
          e.preventDefault();
        }
      }
    }

    element.addEventListener('keydown', handleKeyDown);
    first?.focus();

    return () => element.removeEventListener('keydown', handleKeyDown);
  }, [ref]);
}
```

---

## Anti-Patterns

| Anti-Pattern | Problem | Solution |
|---|---|---|
| Boolean prop explosion | `<Button primary large disabled loading>` | Variant props with CVA: `variant="primary" size="lg"` |
| Hardcoded colors in components | Cannot theme, inconsistent | Design tokens + CSS variables |
| No Storybook stories | Components undocumented, untested | Story per variant + interaction tests |
| Wrapping native HTML poorly | Breaks accessibility, loses features | Forward refs, spread remaining props |
| Styling with inline styles | No theming, no responsive, no hover | Tailwind/CVA or CSS modules |
| No dark mode support | Excludes users, looks unprofessional | Semantic tokens with light/dark themes |
| Tight coupling to framework | Cannot share across React/Vue/Svelte | Headless components + framework adapters |
| No accessibility testing | Excludes users, legal liability | Storybook a11y addon + axe-core in CI |
