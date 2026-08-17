import { Ionicons } from '@expo/vector-icons';
import { useEffect, useRef, useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { Text } from './Text';
import { colors } from './tokens';

export type InputVariant =
  | 'text'
  | 'phone'
  | 'search'
  | 'otp'
  | 'email'
  | 'password';

export interface InputProps {
  variant?: InputVariant;
  value: string;
  onChangeText: (text: string) => void;
  label?: string;
  placeholder?: string;
  /** Renders inline below the field; for variant='otp' also triggers a
   * shake on the box row when it transitions from falsy -> truthy. */
  error?: string;
  disabled?: boolean;
  autoFocus?: boolean;
  // phone variant only
  countryCode?: string;
  onCountryCodePress?: () => void;
  // otp variant only
  length?: number;
  onComplete?: (code: string) => void;
  // search variant only
  onClear?: () => void;
  // text variant only (SS-015: user_notes multiline field with a hard cap)
  multiline?: boolean;
  maxLength?: number;
  // SS-072: email + password variants. Optional with a variant-named
  // fallback below, but in practice a screen with both fields on it must
  // pass distinct explicit labels — see the fallback's own comment.
  accessibilityLabel?: string;
  // password variant only — drives autoComplete/textContentType so a
  // password manager offers "save new password" on signup vs. "fill" on
  // sign-in, per docs/tickets/SS-072-design.md's Deviation 3.
  passwordMode?: 'current' | 'new';
}

const DEFAULT_OTP_LENGTH = 6;
const SHAKE_OFFSET_PX = 8;
const SHAKE_STEP_MS = 50;

// BL-007 (docs/BACKLOG.md, Open): no semantic error colour exists in the
// design tokens yet — this reads the single parked placeholder in
// tokens.ts (`colors.accent.errorPlaceholder`) so there is exactly one
// place to change once BL-007 is resolved, not scattered hex values.
const ERROR_COLOR = colors.accent.errorPlaceholder;

function baseFieldClassName(disabled: boolean, hasError: boolean): string {
  return [
    'rounded-md border px-md py-sm font-body text-base text-textPrimary',
    disabled ? 'bg-surfaceSecondary' : 'bg-surfacePrimary',
    hasError ? '' : 'border-textMuted',
  ]
    .filter(Boolean)
    .join(' ');
}

function ErrorText({ error }: { error?: string }) {
  if (!error) return null;
  return (
    <Text variant="caption" style={{ color: ERROR_COLOR }} className="mt-xs">
      {error}
    </Text>
  );
}

function FieldLabel({ label }: { label?: string }) {
  if (!label) return null;
  return (
    <Text variant="caption" color="secondary" className="mb-xs">
      {label}
    </Text>
  );
}

function OtpInput({
  value,
  onChangeText,
  error,
  disabled,
  autoFocus,
  length = DEFAULT_OTP_LENGTH,
  onComplete,
}: InputProps) {
  const shakeX = useSharedValue(0);
  const prevHadErrorRef = useRef(false);
  // (QA-blocker fix pass, 2026-07-22 — cross-ticket: this component
  // originates in SS-008's design system, consumed by SS-003's
  // verify-otp.tsx, fixed here during SS-004's manual-walkthrough blocker
  // pass — same precedent as BL-014/015/016/021.) The hidden TextInput
  // below does actually receive focus/input (blind typing works), but
  // nothing ever surfaced that to the visible boxes, so the input looked
  // broken. `isFocused` tracks the hidden input's focus state so the box at
  // the "next digit lands here" position can be visually highlighted.
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => {
    const hasError = Boolean(error);
    if (hasError && !prevHadErrorRef.current) {
      shakeX.value = withSequence(
        withTiming(-SHAKE_OFFSET_PX, { duration: SHAKE_STEP_MS }),
        withTiming(SHAKE_OFFSET_PX, { duration: SHAKE_STEP_MS }),
        withTiming(-SHAKE_OFFSET_PX, { duration: SHAKE_STEP_MS }),
        withTiming(SHAKE_OFFSET_PX, { duration: SHAKE_STEP_MS }),
        withTiming(0, { duration: SHAKE_STEP_MS }),
      );
    }
    prevHadErrorRef.current = hasError;
  }, [error, shakeX]);

  const shakeStyle = useAnimatedStyle(() => ({
    flexDirection: 'row',
    transform: [{ translateX: shakeX.value }],
  }));

  const handleChangeText = (text: string) => {
    const digitsOnly = text.replace(/\D/g, '').slice(0, length);
    onChangeText(digitsOnly);
    if (digitsOnly.length === length) {
      onComplete?.(digitsOnly);
    }
  };

  const boxes = Array.from({ length }, (_, index) => value[index] ?? '');
  // The box where the next typed digit will land — clamped so a fully
  // filled value (value.length === length) still highlights the last box
  // rather than pointing one past the end.
  const activeIndex = Math.min(value.length, length - 1);

  return (
    <View>
      {/* NativeWind's className interop doesn't cover reanimated's
       * Animated.View, so flex-row is set via the animated style object
       * instead — a plain `className="flex-row"` here is silently dropped. */}
      <Animated.View style={shakeStyle}>
        {boxes.map((digit, index) => {
          const isActive = isFocused && index === activeIndex;
          // Reuses this design system's existing conventions rather than
          // inventing a new focus colour: `accent.peacock` is the
          // interactive-accent border already used for Button's secondary
          // variant, and the 2px border width already denotes "this is the
          // active one" per Badge's `selected` treatment.
          const borderColor = error
            ? ERROR_COLOR
            : isActive
              ? colors.accent.peacock
              : colors.text.muted;
          return (
            <View
              // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length box positions, not a reorderable list
              key={index}
              testID={`otp-box-${index}`}
              className={`mr-xs h-12 w-10 items-center justify-center rounded-md ${
                isActive ? 'border-2' : 'border'
              }`}
              style={{ borderColor }}
            >
              <Text variant="mono">{digit}</Text>
            </View>
          );
        })}
      </Animated.View>
      <TextInput
        testID="otp-hidden-input"
        value={value}
        onChangeText={handleChangeText}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        keyboardType="number-pad"
        maxLength={length}
        autoFocus={autoFocus}
        editable={!disabled}
        // Visually hidden but present so paste-fills-all-boxes works via a
        // single underlying TextInput receiving one onChangeText call.
        style={{ position: 'absolute', opacity: 0, height: 48, width: '100%' }}
        accessibilityLabel="One-time password"
      />
      <ErrorText error={error} />
    </View>
  );
}

function PhoneInput({
  value,
  onChangeText,
  placeholder,
  error,
  disabled,
  autoFocus,
  countryCode = '+91',
  onCountryCodePress,
}: InputProps) {
  return (
    <View>
      <View className="flex-row items-center">
        <Pressable
          onPress={onCountryCodePress}
          accessibilityRole="button"
          accessibilityLabel="Change country code"
          className="mr-xs rounded-md border border-textMuted bg-surfaceSecondary px-sm py-sm"
        >
          <Text variant="body">{countryCode}</Text>
        </Pressable>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          keyboardType="phone-pad"
          autoFocus={autoFocus}
          editable={!disabled}
          maxLength={10}
          className={`flex-1 ${baseFieldClassName(Boolean(disabled), Boolean(error))}`}
          style={{ borderColor: error ? ERROR_COLOR : undefined }}
          accessibilityLabel="Phone number"
        />
      </View>
      <ErrorText error={error} />
    </View>
  );
}

function SearchInput({
  value,
  onChangeText,
  placeholder,
  disabled,
  autoFocus,
  onClear,
}: InputProps) {
  const handleClear = () => {
    onChangeText('');
    onClear?.();
  };

  return (
    <View className="flex-row items-center rounded-md border border-textMuted bg-surfacePrimary px-sm">
      <Ionicons name="search" size={18} color={colors.text.muted} />
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        editable={!disabled}
        autoFocus={autoFocus}
        className="ml-xs flex-1 py-sm font-body text-base text-textPrimary"
        accessibilityLabel="Search"
      />
      {value.length > 0 ? (
        <Pressable
          onPress={handleClear}
          accessibilityRole="button"
          accessibilityLabel="Clear search"
        >
          <Ionicons name="close-circle" size={18} color={colors.text.muted} />
        </Pressable>
      ) : null}
    </View>
  );
}

function TextVariantInput({
  value,
  onChangeText,
  placeholder,
  error,
  disabled,
  autoFocus,
  multiline = false,
  maxLength,
}: InputProps) {
  return (
    <View>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        editable={!disabled}
        autoFocus={autoFocus}
        multiline={multiline}
        maxLength={maxLength}
        className={baseFieldClassName(Boolean(disabled), Boolean(error))}
        style={{
          borderColor: error ? ERROR_COLOR : undefined,
          ...(multiline ? { minHeight: 80, textAlignVertical: 'top' } : null),
        }}
        accessibilityLabel={placeholder ?? 'Text input'}
      />
      <ErrorText error={error} />
    </View>
  );
}

// SS-072 (Deviation 3) — a password field is unrenderable with plain
// TextVariantInput (no secureTextEntry forwarded), and the missing
// autoCapitalize="none" on a bare text field would manufacture the exact
// `User@x.com` case-variant duplicates this ticket exists to reject. Added
// additively rather than passed-through raw props on the text variant, so
// email/password stay design-system decisions rather than a bypassable
// thin TextInput wrapper (see the design doc's own reasoning).
function EmailInput({
  value,
  onChangeText,
  placeholder,
  error,
  disabled,
  autoFocus,
  accessibilityLabel,
}: InputProps) {
  return (
    <View>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        editable={!disabled}
        autoFocus={autoFocus}
        keyboardType="email-address"
        autoCapitalize="none"
        autoCorrect={false}
        autoComplete="email"
        textContentType="emailAddress"
        className={baseFieldClassName(Boolean(disabled), Boolean(error))}
        style={{ borderColor: error ? ERROR_COLOR : undefined }}
        accessibilityLabel={accessibilityLabel ?? 'Email'}
      />
      <ErrorText error={error} />
    </View>
  );
}

function passwordContainerClassName(
  disabled: boolean,
  hasError: boolean,
): string {
  return [
    'flex-row items-center rounded-md border px-md py-sm',
    disabled ? 'bg-surfaceSecondary' : 'bg-surfacePrimary',
    hasError ? '' : 'border-textMuted',
  ]
    .filter(Boolean)
    .join(' ');
}

// [VERIFIED 2026-08-17 against installed react-native-web@`node_modules/
// react-native-web/dist/cjs/exports/TextInput/index.js:352`] — autoComplete
// is forwarded to the DOM `autocomplete` attribute verbatim, with no RN ->
// web value remapping. RN's own TextInput.d.ts already uses the HTML-spec
// values directly ('current-password' / 'new-password', not 'password' /
// 'password-new'), so using them here needs no adjustment for web, this
// app's primary target.
function PasswordInput({
  value,
  onChangeText,
  placeholder,
  error,
  disabled,
  autoFocus,
  accessibilityLabel,
  passwordMode = 'current',
}: InputProps) {
  const [isVisible, setIsVisible] = useState(false);
  const isNew = passwordMode === 'new';

  return (
    <View>
      <View
        className={passwordContainerClassName(
          Boolean(disabled),
          Boolean(error),
        )}
        style={{ borderColor: error ? ERROR_COLOR : undefined }}
      >
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          editable={!disabled}
          autoFocus={autoFocus}
          secureTextEntry={!isVisible}
          autoCapitalize="none"
          autoCorrect={false}
          autoComplete={isNew ? 'new-password' : 'current-password'}
          textContentType={isNew ? 'newPassword' : 'password'}
          className="flex-1 font-body text-base text-textPrimary"
          accessibilityLabel={accessibilityLabel ?? 'Password'}
        />
        <Pressable
          onPress={() => setIsVisible((visible) => !visible)}
          accessibilityRole="button"
          accessibilityLabel={isVisible ? 'Hide password' : 'Show password'}
        >
          <Ionicons
            name={isVisible ? 'eye-off' : 'eye'}
            size={18}
            color={colors.text.muted}
          />
        </Pressable>
      </View>
      <ErrorText error={error} />
    </View>
  );
}

export function Input(props: InputProps) {
  const { variant = 'text', label } = props;

  return (
    <View>
      <FieldLabel label={label} />
      {variant === 'otp' ? <OtpInput {...props} /> : null}
      {variant === 'phone' ? <PhoneInput {...props} /> : null}
      {variant === 'search' ? <SearchInput {...props} /> : null}
      {variant === 'text' ? <TextVariantInput {...props} /> : null}
      {variant === 'email' ? <EmailInput {...props} /> : null}
      {variant === 'password' ? <PasswordInput {...props} /> : null}
    </View>
  );
}
