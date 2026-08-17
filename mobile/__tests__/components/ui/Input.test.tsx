import { fireEvent, render } from '@testing-library/react-native';
import { Input } from '../../../components/ui/Input';

describe('Input', () => {
  describe('variant="phone"', () => {
    it('renders the +91 prefix by default and fires onCountryCodePress on tap', async () => {
      const onCountryCodePress = jest.fn();
      const { getByText } = await render(
        <Input
          variant="phone"
          value=""
          onChangeText={jest.fn()}
          onCountryCodePress={onCountryCodePress}
        />,
      );
      fireEvent.press(getByText('+91'));
      expect(onCountryCodePress).toHaveBeenCalledTimes(1);
    });

    it('renders a custom country code when provided', async () => {
      const { getByText } = await render(
        <Input
          variant="phone"
          value=""
          onChangeText={jest.fn()}
          countryCode="+1"
        />,
      );
      expect(getByText('+1')).toBeOnTheScreen();
    });
  });

  describe('variant="otp"', () => {
    it('calls onComplete with the full code once length digits are entered', async () => {
      const onComplete = jest.fn();
      const { getByTestId } = await render(
        <Input
          variant="otp"
          length={6}
          value=""
          onChangeText={jest.fn()}
          onComplete={onComplete}
        />,
      );
      fireEvent.changeText(getByTestId('otp-hidden-input'), '123456');
      expect(onComplete).toHaveBeenCalledWith('123456');
    });

    it('does not call onComplete when fewer than length digits are entered', async () => {
      const onComplete = jest.fn();
      const { getByTestId } = await render(
        <Input
          variant="otp"
          length={6}
          value=""
          onChangeText={jest.fn()}
          onComplete={onComplete}
        />,
      );
      fireEvent.changeText(getByTestId('otp-hidden-input'), '123');
      expect(onComplete).not.toHaveBeenCalled();
    });

    it('strips non-digit characters before calling onChangeText', async () => {
      const onChangeText = jest.fn();
      const { getByTestId } = await render(
        <Input variant="otp" length={6} value="" onChangeText={onChangeText} />,
      );
      fireEvent.changeText(getByTestId('otp-hidden-input'), 'a1b2c3');
      expect(onChangeText).toHaveBeenCalledWith('123');
    });

    it('highlights the active box (peacock border) on focus and reverts on blur', async () => {
      const { getByTestId } = await render(
        <Input variant="otp" length={6} value="" onChangeText={jest.fn()} />,
      );
      const hiddenInput = getByTestId('otp-hidden-input');
      const firstBox = getByTestId('otp-box-0');

      // Before focus: no box is highlighted (muted border, default width).
      expect(firstBox.props.style).toMatchObject({ borderColor: '#9A9590' });

      await fireEvent(hiddenInput, 'focus');
      expect(getByTestId('otp-box-0').props.style).toMatchObject({
        borderColor: '#0D6B6E',
      });

      await fireEvent(hiddenInput, 'blur');
      expect(getByTestId('otp-box-0').props.style).toMatchObject({
        borderColor: '#9A9590',
      });
    });

    it('highlights the box at value.length (next digit lands there), not always box 0', async () => {
      const { getByTestId } = await render(
        <Input variant="otp" length={6} value="12" onChangeText={jest.fn()} />,
      );
      const hiddenInput = getByTestId('otp-hidden-input');

      await fireEvent(hiddenInput, 'focus');

      expect(getByTestId('otp-box-2').props.style).toMatchObject({
        borderColor: '#0D6B6E',
      });
      expect(getByTestId('otp-box-0').props.style).toMatchObject({
        borderColor: '#9A9590',
      });
    });

    it('renders an inline error and does not throw when error transitions from falsy to truthy', async () => {
      const { rerender, getByText, queryByText } = await render(
        <Input variant="otp" value="123456" onChangeText={jest.fn()} />,
      );
      expect(queryByText('Invalid code')).toBeNull();

      await rerender(
        <Input
          variant="otp"
          value="123456"
          onChangeText={jest.fn()}
          error="Invalid code"
        />,
      );
      expect(getByText('Invalid code')).toBeOnTheScreen();
    });
  });

  describe('variant="search"', () => {
    it('shows the clear icon only when value is non-empty and fires onClear on press', async () => {
      const onClear = jest.fn();
      const { getByLabelText, queryByLabelText, rerender } = await render(
        <Input
          variant="search"
          value=""
          onChangeText={jest.fn()}
          onClear={onClear}
        />,
      );
      expect(queryByLabelText('Clear search')).toBeNull();

      await rerender(
        <Input
          variant="search"
          value="dress"
          onChangeText={jest.fn()}
          onClear={onClear}
        />,
      );
      fireEvent.press(getByLabelText('Clear search'));
      expect(onClear).toHaveBeenCalledTimes(1);
    });
  });

  describe('variant="text"', () => {
    it('renders the error text below the field when set', async () => {
      const { getByText } = await render(
        <Input
          variant="text"
          value=""
          onChangeText={jest.fn()}
          error="This field is required"
        />,
      );
      expect(getByText('This field is required')).toBeOnTheScreen();
    });

    it('renders no error text when error is unset', async () => {
      const { queryByText } = await render(
        <Input variant="text" value="" onChangeText={jest.fn()} />,
      );
      expect(queryByText('This field is required')).toBeNull();
    });

    it('renders the label when provided', async () => {
      const { getByText } = await render(
        <Input variant="text" value="" onChangeText={jest.fn()} label="Name" />,
      );
      expect(getByText('Name')).toBeOnTheScreen();
    });
  });

  // SS-072 (Deviation 3) — email/password variants.
  describe('variant="email"', () => {
    it('sets autoCapitalize="none" and keyboardType="email-address" (the duplicate-prevention mechanism, not styling)', async () => {
      const { getByLabelText } = await render(
        <Input
          variant="email"
          value=""
          onChangeText={jest.fn()}
          accessibilityLabel="Email address"
        />,
      );
      const field = getByLabelText('Email address');
      expect(field.props.autoCapitalize).toBe('none');
      expect(field.props.keyboardType).toBe('email-address');
    });

    it('renders the inline error string when set', async () => {
      const { getByText } = await render(
        <Input
          variant="email"
          value=""
          onChangeText={jest.fn()}
          error="Please enter a valid email address."
        />,
      );
      expect(
        getByText('Please enter a valid email address.'),
      ).toBeOnTheScreen();
    });
  });

  describe('variant="password"', () => {
    it('renders a masked field by default and the show/hide toggle flips it, with the accessibility label changing', async () => {
      const { getByLabelText, queryByLabelText } = await render(
        <Input
          variant="password"
          value="hunter2"
          onChangeText={jest.fn()}
          accessibilityLabel="Password"
        />,
      );
      const field = getByLabelText('Password');
      expect(field.props.secureTextEntry).toBe(true);
      expect(queryByLabelText('Show password')).toBeOnTheScreen();

      await fireEvent.press(getByLabelText('Show password'));

      expect(getByLabelText('Password').props.secureTextEntry).toBe(false);
      expect(getByLabelText('Hide password')).toBeOnTheScreen();
      expect(queryByLabelText('Show password')).toBeNull();
    });

    it('renders the inline error string when set', async () => {
      const { getByText } = await render(
        <Input
          variant="password"
          value=""
          onChangeText={jest.fn()}
          error="Password must be at least 8 characters."
        />,
      );
      expect(
        getByText('Password must be at least 8 characters.'),
      ).toBeOnTheScreen();
    });
  });
});
