import { describe, expect, it } from 'vitest'
import Skeleton from './Skeleton'

describe('Skeleton', () => {
  it('renders a card skeleton by default', () => {
    const el = Skeleton({})
    expect(el).not.toBeNull()
    expect(el.props.className).toContain('flex')
    expect(el.props.className).toContain('rounded-card')
  });

  it('renders a circle skeleton when variant is circle', () => {
    const el = Skeleton({ variant: 'circle' })
    expect(el).not.toBeNull()
    expect(el.props.className).toContain('rounded-full')
  });

  it('renders a text skeleton when variant is text', () => {
    const el = Skeleton({ variant: 'text' })
    expect(el).not.toBeNull()
    expect(el.props.className).toContain('h-4')
  });

  it('renders multiple skeletons when count is specified', () => {
    const el = Skeleton({ count: 3 })
    expect(el).not.toBeNull()
    expect(el.props.className).toContain('flex-col')
    expect(el.props.children).toHaveLength(3)
  });

  it('marks a single skeleton as a loading status for screen readers', () => {
    const el = Skeleton({})
    expect(el.props.role).toBe('status')
    expect(el.props['aria-label']).toBe('Loading')
  });

  it('exposes the status on the wrapper and hides list items from screen readers', () => {
    const el = Skeleton({ count: 3 })
    expect(el.props.role).toBe('status')
    expect(el.props['aria-label']).toBe('Loading')
    expect(el.props.children[0].props['aria-hidden']).toBe('true')
  });
})
