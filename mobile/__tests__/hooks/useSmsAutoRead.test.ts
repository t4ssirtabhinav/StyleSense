import { renderHook } from '@testing-library/react-native';
import { Platform } from 'react-native';
import { useSmsAutoRead } from '../../hooks/useSmsAutoRead';

describe('useSmsAutoRead', () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('is a guaranteed no-op on iOS — no SMS Retriever/User Consent API exists there', () => {
    jest.replaceProperty(Platform, 'OS', 'ios');
    const onCodeReceived = jest.fn();

    expect(() =>
      renderHook(() => useSmsAutoRead(onCodeReceived)),
    ).not.toThrow();
    expect(onCodeReceived).not.toHaveBeenCalled();
  });

  it('is a guaranteed no-op on web — no SMS Retriever/User Consent API exists there', () => {
    jest.replaceProperty(Platform, 'OS', 'web');
    const onCodeReceived = jest.fn();

    expect(() =>
      renderHook(() => useSmsAutoRead(onCodeReceived)),
    ).not.toThrow();
    expect(onCodeReceived).not.toHaveBeenCalled();
  });

  it('does not throw on android either — intentionally a documented no-op stub pending a package decision (BL-019), not a real integration', () => {
    jest.replaceProperty(Platform, 'OS', 'android');
    const onCodeReceived = jest.fn();

    expect(() =>
      renderHook(() => useSmsAutoRead(onCodeReceived)),
    ).not.toThrow();
    expect(onCodeReceived).not.toHaveBeenCalled();
  });
});
