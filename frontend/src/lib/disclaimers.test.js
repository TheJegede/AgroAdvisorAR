import { describe, expect, it } from 'vitest';
import { SPRAY_DISCLAIMER_EN, SPRAY_DISCLAIMER_ES } from './disclaimers';

describe('Spray Check Disclaimers', () => {
  it('has non-empty English disclaimer', () => {
    expect(SPRAY_DISCLAIMER_EN).toBeTruthy();
    expect(typeof SPRAY_DISCLAIMER_EN).toBe('string');
    expect(SPRAY_DISCLAIMER_EN.length).toBeGreaterThan(20);
  });

  it('has non-empty Spanish disclaimer', () => {
    expect(SPRAY_DISCLAIMER_ES).toBeTruthy();
    expect(typeof SPRAY_DISCLAIMER_ES).toBe('string');
    expect(SPRAY_DISCLAIMER_ES.length).toBeGreaterThan(20);
  });

  it('English and Spanish disclaimers are distinct', () => {
    expect(SPRAY_DISCLAIMER_EN).not.toBe(SPRAY_DISCLAIMER_ES);
  });
});
